#!/usr/bin/env python3
"""Run one B0 experiment command under fail-closed macOS resource guards.

The wrapper never invokes a shell.  It creates all evidence files exclusively,
places the child in a new process group, polls descendant RSS and system swap
at a high-frequency cadence, and records disk/evidence heartbeats separately.
It terminates the complete process group when a registered guard is crossed.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import importlib
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


SCHEMA_VERSION = "b0-monitored-command-v1"
GIB = 1024**3
DEFAULT_START_AVAILABLE_BYTES = 15 * GIB
DEFAULT_STOP_AVAILABLE_BYTES = 6 * GIB
DEFAULT_PEAK_RSS_BYTES = 12 * GIB
DEFAULT_SWAP_GROWTH_BYTES = 4 * GIB
DEFAULT_SAMPLE_INTERVAL_SECONDS = 1800.0
DEFAULT_RESOURCE_POLL_SECONDS = 1.0
DEFAULT_WALL_TIMEOUT_SECONDS = 4.0 * 60.0 * 60.0
MAX_SAMPLE_INTERVAL_SECONDS = 30.0 * 60.0
MAX_RESOURCE_POLL_SECONDS = 5.0

DEFAULT_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PYTHONPATH",
    "DYLD_LIBRARY_PATH",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "MKL_NUM_THREADS",
    "PYTHONHASHSEED",
)
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PHASE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PLACEHOLDER_RE = re.compile(r"<[^<>]+>")
_SWAP_USED_RE = re.compile(
    r"\bused\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT])(?:i?B)?\b",
    flags=re.IGNORECASE,
)


class ConfigurationError(ValueError):
    """Raised before a command is launched when the contract is invalid."""


class FormalBindingError(ConfigurationError):
    """Raised when a formal run differs from its preregistered identity."""


class AttestationError(ConfigurationError):
    """Raised when a requested post-run artifact cannot be attested."""


class PriorStatusError(ConfigurationError):
    """Raised when a prerequisite PASS status or its artifacts have drifted."""


@dataclasses.dataclass(frozen=True)
class ProbeResult:
    """One resource observation, with unknown represented explicitly."""

    status: str
    value_bytes: int | None
    error: str | None = None
    details: Mapping[str, Any] = dataclasses.field(default_factory=dict)

    @classmethod
    def known(
        cls, value_bytes: int, *, details: Mapping[str, Any] | None = None
    ) -> "ProbeResult":
        value = int(value_bytes)
        if value < 0:
            raise ValueError("probe byte value cannot be negative")
        return cls("KNOWN", value, None, dict(details or {}))

    @classmethod
    def unknown(cls, error: str) -> "ProbeResult":
        return cls("UNKNOWN", None, str(error), {})

    def as_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "value_bytes": self.value_bytes,
            "error": self.error,
            "details": dict(self.details),
        }


DiskProbe = Callable[[Path], ProbeResult]
RssProbe = Callable[[int], ProbeResult]
SwapProbe = Callable[[], ProbeResult]


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(chunk_size)
            if not block:
                return digest.hexdigest()
            digest.update(block)


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FormalBindingError(f"{label} must be a JSON object")
    return value


def _stable_file_identity(path: Path, *, label: str) -> tuple[int, str]:
    try:
        before = path.stat()
        digest = _sha256_file(path)
        after = path.stat()
    except OSError as exc:
        raise FormalBindingError(f"{label} is unreadable: {path}: {exc}") from exc
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity:
        raise FormalBindingError(f"{label} changed while being hashed: {path}")
    return after.st_size, digest


def _read_verified_contract(path: Path) -> tuple[Mapping[str, Any], str, Path]:
    if not path.is_absolute():
        raise FormalBindingError("preregistered contract path must be absolute")
    resolved = path.resolve()
    if not resolved.is_file():
        raise FormalBindingError(f"preregistered contract is not a file: {resolved}")
    size, digest = _stable_file_identity(
        resolved, label="preregistered contract"
    )
    if size <= 0:
        raise FormalBindingError("preregistered contract is empty")
    sidecar = resolved.with_suffix(".sha256")
    try:
        sidecar_text = sidecar.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FormalBindingError(
            f"preregistered contract hash sidecar is unreadable: {sidecar}: {exc}"
        ) from exc
    expected_sidecar = f"{digest}  {resolved.name}\n"
    if sidecar_text != expected_sidecar:
        raise FormalBindingError(
            "preregistered contract hash sidecar does not match contract bytes"
        )
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FormalBindingError(f"invalid preregistered contract JSON: {exc}") from exc
    contract = _require_mapping(payload, label="preregistered contract")
    if contract.get("schema_version") != "b0-preregistration-v1":
        raise FormalBindingError(
            "preregistered contract schema must be b0-preregistration-v1"
        )
    return contract, digest, sidecar


def _validate_source_bundle(
    source_state: Mapping[str, Any],
) -> tuple[Path, str, Path]:
    bundle = _require_mapping(
        source_state.get("dirty_code_bundle"), label="dirty code bundle"
    )
    files = bundle.get("files")
    if not isinstance(files, list) or not files:
        raise FormalBindingError("dirty code bundle files must be a non-empty array")

    roots: set[Path] = set()
    seen_relative: set[str] = set()
    seen_absolute: set[Path] = set()
    preregister_source: Path | None = None
    normalized_files: list[Mapping[str, Any]] = []
    for index, raw_entry in enumerate(files):
        entry = _require_mapping(raw_entry, label=f"dirty code file {index}")
        relative_value = entry.get("relative_path")
        absolute_value = entry.get("absolute_path")
        expected_size = entry.get("size_bytes")
        expected_sha = entry.get("sha256")
        if not isinstance(relative_value, str) or not relative_value:
            raise FormalBindingError(f"dirty code file {index} has invalid relative_path")
        relative = Path(relative_value)
        if (
            relative.is_absolute()
            or relative_value in seen_relative
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise FormalBindingError(
                f"dirty code file {index} has unsafe or duplicate relative_path"
            )
        if not isinstance(absolute_value, str) or not Path(absolute_value).is_absolute():
            raise FormalBindingError(f"dirty code file {index} path must be absolute")
        absolute = Path(absolute_value)
        resolved = absolute.resolve()
        if resolved != absolute or resolved in seen_absolute:
            raise FormalBindingError(
                f"dirty code file {index} path is noncanonical or duplicate"
            )
        if isinstance(expected_size, bool) or not isinstance(expected_size, int):
            raise FormalBindingError(f"dirty code file {index} size is invalid")
        if not isinstance(expected_sha, str) or not _HEX_SHA256_RE.fullmatch(
            expected_sha
        ):
            raise FormalBindingError(f"dirty code file {index} sha256 is invalid")

        actual_size, actual_sha = _stable_file_identity(
            resolved, label=f"dirty code file {relative_value}"
        )
        if actual_size != expected_size or actual_sha != expected_sha:
            raise FormalBindingError(
                f"dirty code drift for {relative_value}: size or sha256 differs"
            )
        candidate_root = resolved
        for _part in relative.parts:
            candidate_root = candidate_root.parent
        if (candidate_root / relative).resolve() != resolved:
            raise FormalBindingError(
                f"dirty code file {relative_value} does not bind to one code root"
            )
        roots.add(candidate_root)
        seen_relative.add(relative_value)
        seen_absolute.add(resolved)
        normalized_files.append(entry)
        if relative_value == "tools/python/b0_preregister.py":
            preregister_source = resolved

    if len(roots) != 1:
        raise FormalBindingError("dirty code bundle does not have one absolute code root")
    if preregister_source is None:
        raise FormalBindingError("dirty code bundle omits b0_preregister.py")
    bundle_payload = {
        "git_head": bundle.get("git_head"),
        "git_head_contains_experiment_code": bundle.get(
            "git_head_contains_experiment_code"
        ),
        "files": normalized_files,
    }
    expected_bundle_sha = bundle.get("bundle_sha256")
    actual_bundle_sha = _canonical_sha256(bundle_payload)
    if expected_bundle_sha != actual_bundle_sha:
        raise FormalBindingError("dirty code bundle canonical sha256 differs")
    return next(iter(roots)), actual_bundle_sha, preregister_source


def _validate_formal_binding(
    *,
    contract_path: Path,
    phase: str,
    child_argv: Sequence[str],
    child_environment: Mapping[str, str],
) -> dict[str, Any]:
    """Fail closed unless code, binary, environment, and argv match the freeze."""

    if not _PHASE_RE.fullmatch(phase):
        raise FormalBindingError(f"invalid formal phase key: {phase!r}")
    contract, contract_sha, sidecar = _read_verified_contract(contract_path)
    authority = _require_mapping(
        contract.get("frozen_authority"), label="frozen authority"
    )
    source_state = _require_mapping(
        authority.get("source_state"), label="frozen source state"
    )
    code_root, bundle_sha, preregister_source = _validate_source_bundle(source_state)

    binary = _require_mapping(
        authority.get("alicevision_binary"), label="AliceVision binary identity"
    )
    binary_path_value = binary.get("path")
    if not isinstance(binary_path_value, str) or not Path(binary_path_value).is_absolute():
        raise FormalBindingError("AliceVision binary path must be absolute")
    binary_path = Path(binary_path_value)
    if binary_path.resolve() != binary_path:
        raise FormalBindingError("AliceVision binary path must be canonical")
    binary_size, binary_sha = _stable_file_identity(
        binary_path, label="AliceVision binary"
    )
    if (
        binary_size != binary.get("size_bytes")
        or binary_sha != binary.get("sha256")
        or not os.access(binary_path, os.X_OK)
        or binary.get("executable") is not True
    ):
        raise FormalBindingError("AliceVision binary size/sha/executable identity drifted")

    execution_plan = _require_mapping(
        contract.get("execution_plan"), label="execution plan"
    )
    bindings = _require_mapping(
        execution_plan.get("formal_runner_bindings"),
        label="formal runner bindings",
    )
    binding = _require_mapping(bindings.get(phase), label=f"formal phase {phase!r}")
    expected_argv = binding.get("child_argv")
    if (
        not isinstance(expected_argv, list)
        or not expected_argv
        or any(not isinstance(item, str) or "\x00" in item for item in expected_argv)
    ):
        raise FormalBindingError(f"formal phase {phase!r} child_argv is invalid")
    if any(_PLACEHOLDER_RE.search(item) for item in expected_argv):
        raise FormalBindingError(
            f"formal phase {phase!r} child_argv contains unresolved placeholders"
        )
    expected_argv_sha = binding.get("child_argv_sha256")
    actual_expected_sha = _canonical_sha256(expected_argv)
    if expected_argv_sha != actual_expected_sha:
        raise FormalBindingError(
            f"formal phase {phase!r} child_argv canonical sha256 differs"
        )
    actual_argv = list(child_argv)
    if actual_argv != expected_argv:
        raise FormalBindingError(
            f"actual child argv differs from preregistered phase {phase!r}"
        )

    # Import only the exact preregister source already verified above, and do
    # not create bytecode while formal validation is still pre-output.
    old_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        preregister_module = importlib.import_module("b0_preregister")
    except Exception as exc:
        raise FormalBindingError(
            f"cannot import frozen b0_preregister identity helper: {exc}"
        ) from exc
    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
    module_file_value = getattr(preregister_module, "__file__", None)
    if (
        not isinstance(module_file_value, str)
        or Path(module_file_value).resolve() != preregister_source
    ):
        raise FormalBindingError(
            "imported b0_preregister module is not the frozen bundle file"
        )
    freeze_identity = getattr(preregister_module, "_freeze_execution_identity", None)
    if not callable(freeze_identity):
        raise FormalBindingError("b0_preregister identity helper is unavailable")
    try:
        actual_identity = freeze_identity(
            code_root=code_root,
            alicevision_binary=binary_path,
        )
    except Exception as exc:
        raise FormalBindingError(
            f"cannot recompute formal execution identity: {type(exc).__name__}: {exc}"
        ) from exc
    for key in ("source_state", "alicevision_binary", "environment_identity"):
        if actual_identity.get(key) != authority.get(key):
            raise FormalBindingError(f"formal {key} differs from preregistration")

    environment = _require_mapping(
        authority.get("environment_identity"), label="environment identity"
    )
    frozen_environment = _require_mapping(
        environment.get("identity"), label="frozen environment identity payload"
    )
    selected = _require_mapping(
        frozen_environment.get("selected_process_environment"),
        label="selected process environment",
    )
    child_projection = {name: child_environment.get(name) for name in selected}
    if child_projection != dict(selected):
        raise FormalBindingError(
            "child environment projection differs from preregistered environment"
        )

    return {
        "status": "VERIFIED",
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": contract_sha,
        "contract_sidecar_path": str(sidecar),
        "phase": phase,
        "child_argv_sha256": actual_expected_sha,
        "source_bundle_sha256": bundle_sha,
        "alicevision_binary_sha256": binary_sha,
        "environment_sha256": environment.get("sha256"),
        "verified_at_utc": _utc_now(),
    }


def _canonical_absolute_path(value: Path | str, *, label: str) -> Path:
    supplied = Path(value).expanduser()
    if not supplied.is_absolute():
        raise ConfigurationError(f"{label} must be absolute: {supplied}")
    if supplied.is_symlink():
        raise ConfigurationError(f"{label} must not be a symlink: {supplied}")
    resolved = supplied.resolve(strict=False)
    # macOS exposes /var as an alias of /private/var.  Preserve one canonical
    # identity in evidence while accepting an otherwise valid absolute path
    # whose parent traverses that operating-system alias.
    return resolved


def _prepare_attestation_targets(
    files: Sequence[Path | str], trees: Sequence[Path | str]
) -> tuple[list[Path], list[Path]]:
    normalized_files = [
        _canonical_absolute_path(value, label="attest-file") for value in files
    ]
    normalized_trees = [
        _canonical_absolute_path(value, label="attest-tree") for value in trees
    ]
    combined = normalized_files + normalized_trees
    if len(set(combined)) != len(combined):
        raise ConfigurationError("attestation targets must be unique")
    existing = [str(path) for path in combined if os.path.lexists(path)]
    if existing:
        raise ConfigurationError(
            "attestation output target must not exist before child launch: "
            + ", ".join(existing)
        )
    return normalized_files, normalized_trees


def _attest_file(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.resolve(strict=False) != path:
        raise AttestationError(f"attested file is a symlink or noncanonical: {path}")
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise AttestationError(f"attested file is missing: {path}: {exc}") from exc
    if not stat.S_ISREG(mode):
        raise AttestationError(f"attested file is not a regular file: {path}")
    try:
        size, digest = _stable_file_identity(path, label="attested file")
    except FormalBindingError as exc:
        raise AttestationError(str(exc)) from exc
    return {
        "schema_version": "b0-attested-file-v1",
        "path": str(path),
        "size_bytes": size,
        "sha256": digest,
    }


def _collect_tree_layout(
    root: Path,
) -> tuple[
    dict[str, tuple[int, int, int, int, int]],
    list[tuple[str, Path, tuple[int, int, int, int, int]]],
]:
    directories: dict[str, tuple[int, int, int, int, int]] = {}
    files: list[tuple[str, Path, tuple[int, int, int, int, int]]] = []
    for current_value, directory_names, file_names in os.walk(
        root, topdown=True, followlinks=False
    ):
        current = Path(current_value)
        relative_directory = current.relative_to(root).as_posix()
        current_stat = current.lstat()
        if not stat.S_ISDIR(current_stat.st_mode) or current.is_symlink():
            raise AttestationError(f"attested tree contains a non-directory: {current}")
        directories[relative_directory] = (
            current_stat.st_dev,
            current_stat.st_ino,
            current_stat.st_size,
            current_stat.st_mtime_ns,
            current_stat.st_ctime_ns,
        )
        directory_names.sort()
        file_names.sort()
        for name in directory_names:
            child = current / name
            child_stat = child.lstat()
            if child.is_symlink() or not stat.S_ISDIR(child_stat.st_mode):
                raise AttestationError(
                    f"attested tree contains a symlink or special directory: {child}"
                )
        for name in file_names:
            child = current / name
            child_stat = child.lstat()
            if child.is_symlink() or not stat.S_ISREG(child_stat.st_mode):
                raise AttestationError(
                    f"attested tree contains a symlink or special file: {child}"
                )
            files.append(
                (
                    child.relative_to(root).as_posix(),
                    child,
                    (
                        child_stat.st_dev,
                        child_stat.st_ino,
                        child_stat.st_size,
                        child_stat.st_mtime_ns,
                        child_stat.st_ctime_ns,
                    ),
                )
            )
    files.sort(key=lambda item: item[0])
    return directories, files


def _attest_tree(path: Path) -> dict[str, Any]:
    if path.is_symlink() or path.resolve(strict=False) != path:
        raise AttestationError(f"attested tree is a symlink or noncanonical: {path}")
    try:
        root_mode = path.lstat().st_mode
    except OSError as exc:
        raise AttestationError(f"attested tree is missing: {path}: {exc}") from exc
    if not stat.S_ISDIR(root_mode):
        raise AttestationError(f"attested tree is not a directory: {path}")

    before_directories, file_paths = _collect_tree_layout(path)
    file_records: list[dict[str, Any]] = []
    total_size = 0
    for relative, child, _identity in file_paths:
        try:
            size, digest = _stable_file_identity(
                child, label=f"attested tree file {relative}"
            )
        except FormalBindingError as exc:
            raise AttestationError(str(exc)) from exc
        total_size += size
        file_records.append(
            {
                "relative_path": relative,
                "size_bytes": size,
                "sha256": digest,
            }
        )
    after_directories, after_files = _collect_tree_layout(path)
    before_file_identities = [(relative, identity) for relative, _, identity in file_paths]
    after_file_identities = [(relative, identity) for relative, _, identity in after_files]
    if (
        before_directories != after_directories
        or before_file_identities != after_file_identities
    ):
        raise AttestationError(f"attested tree changed while being hashed: {path}")
    tree_payload = {"files": file_records}
    return {
        "schema_version": "b0-attested-tree-v1",
        "path": str(path),
        "file_count": len(file_records),
        "total_size_bytes": total_size,
        "files": file_records,
        "tree_sha256": _canonical_sha256(tree_payload),
    }


def _attest_outputs(files: Sequence[Path], trees: Sequence[Path]) -> dict[str, Any]:
    file_records = [_attest_file(path) for path in files]
    tree_records = [_attest_tree(path) for path in trees]
    payload = {"files": file_records, "trees": tree_records}
    return {
        "status": "VERIFIED",
        **payload,
        "bundle_sha256": _canonical_sha256(payload),
        "verified_at_utc": _utc_now(),
        "error": None,
    }


def _load_prior_status(path: Path) -> tuple[Mapping[str, Any], str]:
    if path.is_symlink() or path.resolve(strict=False) != path:
        raise PriorStatusError(f"prior status is a symlink or noncanonical: {path}")
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise PriorStatusError(f"prior status is missing: {path}: {exc}") from exc
    if not stat.S_ISREG(mode):
        raise PriorStatusError(f"prior status is not a regular file: {path}")
    try:
        _, digest = _stable_file_identity(path, label="prior status")
    except FormalBindingError as exc:
        raise PriorStatusError(str(exc)) from exc
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PriorStatusError(f"prior status is invalid JSON: {path}: {exc}") from exc
    try:
        status = _require_mapping(payload, label="prior status")
    except FormalBindingError as exc:
        raise PriorStatusError(str(exc)) from exc
    return status, digest


def _require_prior_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    try:
        return _require_mapping(value, label=label)
    except FormalBindingError as exc:
        raise PriorStatusError(str(exc)) from exc


def _verify_prior_statuses(
    paths: Sequence[Path | str], *, formal_binding: Mapping[str, Any]
) -> list[dict[str, Any]]:
    normalized = [
        _canonical_absolute_path(value, label="require-prior-status")
        for value in paths
    ]
    if len(set(normalized)) != len(normalized):
        raise PriorStatusError("required prior status paths must be unique")
    results: list[dict[str, Any]] = []
    for path in normalized:
        status, status_sha = _load_prior_status(path)
        if status.get("schema_version") != SCHEMA_VERSION or status.get("verdict") != "PASS":
            raise PriorStatusError(
                f"prior status must be {SCHEMA_VERSION} with PASS verdict: {path}"
        )
        if formal_binding.get("status") == "VERIFIED":
            prior_binding = _require_prior_mapping(
                status.get("formal_binding"), label="prior formal binding"
            )
            for key in ("status", "contract_path", "contract_sha256"):
                if prior_binding.get(key) != formal_binding.get(key):
                    raise PriorStatusError(
                        f"prior formal binding {key} differs for {path}"
                    )
        attestation = _require_prior_mapping(
            status.get("attestation"), label="prior attestation"
        )
        prior_files = attestation.get("files")
        prior_trees = attestation.get("trees")
        if (
            attestation.get("status") != "VERIFIED"
            or not isinstance(prior_files, list)
            or not isinstance(prior_trees, list)
            or not (prior_files or prior_trees)
        ):
            raise PriorStatusError(
                f"prior status lacks a verified non-empty attestation: {path}"
            )
        current_files: list[dict[str, Any]] = []
        for record_value in prior_files:
            record = _require_prior_mapping(
                record_value, label="prior file attestation"
            )
            record_path = record.get("path")
            if not isinstance(record_path, str) or not Path(record_path).is_absolute():
                raise PriorStatusError("prior file attestation path is invalid")
            try:
                current = _attest_file(Path(record_path))
            except AttestationError as exc:
                raise PriorStatusError(str(exc)) from exc
            if current != dict(record):
                raise PriorStatusError(
                    f"prior attested file changed or was replaced: {record_path}"
                )
            current_files.append(current)
        current_trees: list[dict[str, Any]] = []
        for record_value in prior_trees:
            record = _require_prior_mapping(
                record_value, label="prior tree attestation"
            )
            record_path = record.get("path")
            if not isinstance(record_path, str) or not Path(record_path).is_absolute():
                raise PriorStatusError("prior tree attestation path is invalid")
            try:
                current = _attest_tree(Path(record_path))
            except AttestationError as exc:
                raise PriorStatusError(str(exc)) from exc
            if current != dict(record):
                raise PriorStatusError(
                    f"prior attested tree changed or was replaced: {record_path}"
                )
            current_trees.append(current)
        current_payload = {"files": current_files, "trees": current_trees}
        if attestation.get("bundle_sha256") != _canonical_sha256(current_payload):
            raise PriorStatusError(f"prior attestation bundle sha256 differs: {path}")
        results.append(
            {
                "status": "VERIFIED",
                "path": str(path),
                "sha256": status_sha,
                "attestation_bundle_sha256": attestation["bundle_sha256"],
                "formal_contract_sha256": (
                    status.get("formal_binding", {}).get("contract_sha256")
                    if isinstance(status.get("formal_binding"), Mapping)
                    else None
                ),
            }
        )
    return results


def probe_disk_available(path: Path) -> ProbeResult:
    try:
        return ProbeResult.known(shutil.disk_usage(path).free)
    except (OSError, ValueError) as exc:
        return ProbeResult.unknown(f"disk usage unavailable: {exc}")


def parse_swapusage_bytes(output: str) -> int:
    """Parse the used byte count from macOS ``sysctl vm.swapusage`` output."""

    match = _SWAP_USED_RE.search(output)
    if match is None:
        raise ValueError("vm.swapusage output does not contain a parseable used value")
    magnitude = float(match.group(1))
    unit = match.group(2).upper()
    multiplier = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}[unit]
    return int(magnitude * multiplier)


def probe_swapusage() -> ProbeResult:
    command = ["/usr/sbin/sysctl", "vm.swapusage"]
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ProbeResult.unknown(f"sysctl vm.swapusage unavailable: {exc}")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        return ProbeResult.unknown(f"sysctl vm.swapusage failed: {detail}")
    try:
        return ProbeResult.known(parse_swapusage_bytes(completed.stdout))
    except ValueError as exc:
        return ProbeResult.unknown(str(exc))


def process_tree_rss_from_ps(listing: str, *, root_pid: int) -> tuple[int, int]:
    """Sum RSS KiB for ``root_pid`` and every transitive descendant."""

    rows: dict[int, tuple[int, int]] = {}
    children: dict[int, list[int]] = {}
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            pid, ppid, rss_kib = (int(field) for field in fields)
        except ValueError:
            continue
        if pid <= 0 or ppid < 0 or rss_kib < 0:
            continue
        rows[pid] = (ppid, rss_kib)
        children.setdefault(ppid, []).append(pid)

    pending = [int(root_pid)]
    visited: set[int] = set()
    rss_kib_total = 0
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        row = rows.get(pid)
        if row is None:
            continue
        rss_kib_total += row[1]
        pending.extend(children.get(pid, ()))
    present = visited & rows.keys()
    return rss_kib_total * 1024, len(present)


def probe_process_tree_rss(root_pid: int) -> ProbeResult:
    try:
        completed = subprocess.run(
            ["/bin/ps", "-axo", "pid=,ppid=,rss="],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ProbeResult.unknown(f"process-tree RSS unavailable: {exc}")
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        return ProbeResult.unknown(f"ps process-tree RSS failed: {detail}")
    rss_bytes, process_count = process_tree_rss_from_ps(
        completed.stdout, root_pid=root_pid
    )
    return ProbeResult.known(rss_bytes, details={"process_count": process_count})


def _safe_probe(function: Callable[..., ProbeResult], *args: object) -> ProbeResult:
    try:
        result = function(*args)
    except Exception as exc:  # A monitoring failure must be evidence, not a crash.
        return ProbeResult.unknown(f"{type(exc).__name__}: {exc}")
    if not isinstance(result, ProbeResult):
        return ProbeResult.unknown(
            f"probe returned {type(result).__name__}, expected ProbeResult"
        )
    if result.status not in {"KNOWN", "UNKNOWN"}:
        return ProbeResult.unknown(f"probe returned invalid status {result.status!r}")
    return result


def _validate_positive_finite(value: float, *, label: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0.0:
        raise ConfigurationError(f"{label} must be finite and > 0")
    return number


def _validate_nonnegative_int(value: int, *, label: str) -> int:
    number = int(value)
    if number < 0:
        raise ConfigurationError(f"{label} must be >= 0")
    return number


def _prepare_environment(
    allowlist: Sequence[str], overrides: Mapping[str, str]
) -> tuple[list[str], dict[str, str]]:
    ordered: list[str] = []
    seen: set[str] = set()
    for name in tuple(allowlist) + tuple(overrides):
        if not _ENV_NAME_RE.fullmatch(name):
            raise ConfigurationError(f"invalid environment name: {name!r}")
        if name not in seen:
            ordered.append(name)
            seen.add(name)
    effective = {name: os.environ[name] for name in ordered if name in os.environ}
    for name, value in overrides.items():
        if "\x00" in value:
            raise ConfigurationError(f"environment value for {name!r} contains NUL")
        effective[name] = str(value)
    return ordered, effective


def _derived_log_paths(status_path: Path) -> tuple[Path, Path]:
    stem = (
        status_path.name[: -len(status_path.suffix)]
        if status_path.suffix
        else status_path.name
    )
    return (
        status_path.with_name(f"{stem}.stdout.log"),
        status_path.with_name(f"{stem}.stderr.log"),
    )


def _reserve_output_paths(paths: Sequence[Path]) -> None:
    normalized = [path.expanduser().absolute() for path in paths]
    if len(set(normalized)) != len(normalized):
        raise ConfigurationError("resource, status, stdout, and stderr paths must differ")
    collisions = [
        str(path) for path in normalized if path.exists() or path.is_symlink()
    ]
    if collisions:
        raise FileExistsError("refusing to overwrite output: " + ", ".join(collisions))
    for path in normalized:
        path.parent.mkdir(parents=True, exist_ok=True)


def _append_sample(stream: Any, sample: Mapping[str, Any]) -> None:
    stream.write(json.dumps(sample, ensure_ascii=False, sort_keys=True) + "\n")
    stream.flush()


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(
    process: subprocess.Popen[bytes], *, grace_seconds: float
) -> tuple[bool, bool]:
    """Terminate the new-session process group; return (signalled, SIGKILL used)."""

    signalled = False
    escalated = False
    try:
        os.killpg(process.pid, signal.SIGTERM)
        signalled = True
    except ProcessLookupError:
        return False, False
    except OSError:
        # The process was launched in a new session, but retain a PID fallback
        # for the narrow race where group lookup fails during teardown.
        if process.poll() is None:
            try:
                process.terminate()
                signalled = True
            except OSError:
                return False, False
        else:
            return False, False

    def group_exists() -> bool:
        # Reap the direct child promptly; an unreaped zombie keeps its process
        # group observable and would otherwise force a needless grace delay.
        process.poll()
        return _process_group_exists(process.pid)

    deadline = time.monotonic() + max(0.0, grace_seconds)
    while group_exists() and time.monotonic() < deadline:
        time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))
    if group_exists():
        try:
            os.killpg(process.pid, signal.SIGKILL)
            escalated = True
        except ProcessLookupError:
            pass
        except OSError:
            try:
                process.kill()
                escalated = True
            except OSError:
                pass
        kill_deadline = time.monotonic() + 1.0
        while group_exists() and time.monotonic() < kill_deadline:
            time.sleep(0.01)
    try:
        process.wait(timeout=max(1.0, grace_seconds))
    except subprocess.TimeoutExpired:
        pass
    return signalled, escalated


def _metric_summary(
    *,
    observations: Sequence[ProbeResult],
    start_value: int | None,
    end_value: int | None,
    minimum_value: int | None = None,
    peak_value: int | None = None,
    peak_growth: int | None = None,
) -> dict[str, Any]:
    errors = sorted(
        {observation.error for observation in observations if observation.error}
    )
    if not observations:
        errors.append("no observations")
    status = (
        "UNKNOWN"
        if errors or any(o.status == "UNKNOWN" for o in observations)
        else "KNOWN"
    )
    return {
        "status": status,
        "start_bytes": start_value,
        "end_bytes": end_value,
        "minimum_available_bytes": minimum_value,
        "peak_bytes": peak_value,
        "peak_growth_bytes": peak_growth,
        "errors": errors,
    }


def run_monitored(
    argv: Sequence[str],
    *,
    resource_log: Path | str,
    status_path: Path | str,
    disk_path: Path | str = Path("/"),
    label: str = "b0-command",
    env_allowlist: Sequence[str] = DEFAULT_ENV_ALLOWLIST,
    env_overrides: Mapping[str, str] | None = None,
    start_available_bytes: int = DEFAULT_START_AVAILABLE_BYTES,
    stop_available_bytes: int = DEFAULT_STOP_AVAILABLE_BYTES,
    sample_interval_seconds: float = DEFAULT_SAMPLE_INTERVAL_SECONDS,
    peak_rss_bytes: int = DEFAULT_PEAK_RSS_BYTES,
    swap_growth_bytes: int = DEFAULT_SWAP_GROWTH_BYTES,
    wall_timeout_seconds: float = DEFAULT_WALL_TIMEOUT_SECONDS,
    resource_poll_seconds: float = DEFAULT_RESOURCE_POLL_SECONDS,
    disk_probe: DiskProbe = probe_disk_available,
    rss_probe: RssProbe = probe_process_tree_rss,
    swap_probe: SwapProbe = probe_swapusage,
    termination_grace_seconds: float = 10.0,
    preregistered_contract: Path | str | None = None,
    phase: str | None = None,
    attest_files: Sequence[Path | str] = (),
    attest_trees: Sequence[Path | str] = (),
    require_prior_statuses: Sequence[Path | str] = (),
) -> dict[str, Any]:
    """Execute ``argv`` and return the exact JSON object written to status."""

    command = [str(part) for part in argv]
    if not command or any("\x00" in part for part in command):
        raise ConfigurationError("command must be a non-empty NUL-free argv")
    if not label or "\x00" in label:
        raise ConfigurationError("label must be non-empty and NUL-free")
    interval = _validate_positive_finite(
        sample_interval_seconds, label="sample interval"
    )
    if interval > MAX_SAMPLE_INTERVAL_SECONDS:
        raise ConfigurationError("sample interval must be <= 1800 seconds")
    resource_poll = _validate_positive_finite(
        resource_poll_seconds, label="resource poll interval"
    )
    if resource_poll > min(MAX_RESOURCE_POLL_SECONDS, interval):
        raise ConfigurationError(
            "resource poll interval must be <= min(5 seconds, sample interval)"
        )
    timeout = _validate_positive_finite(wall_timeout_seconds, label="wall timeout")
    grace = _validate_positive_finite(
        termination_grace_seconds, label="termination grace"
    )
    start_limit = _validate_nonnegative_int(
        start_available_bytes, label="start available bytes"
    )
    stop_limit = _validate_nonnegative_int(
        stop_available_bytes, label="stop available bytes"
    )
    if start_limit <= stop_limit:
        raise ConfigurationError("start disk threshold must exceed stop threshold")
    rss_limit = _validate_nonnegative_int(
        peak_rss_bytes,
        label="peak RSS bytes",
    )
    swap_limit = _validate_nonnegative_int(
        swap_growth_bytes, label="swap growth bytes"
    )
    overrides = dict(env_overrides or {})
    allowlist, child_env = _prepare_environment(env_allowlist, overrides)

    if (preregistered_contract is None) != (phase is None):
        raise ConfigurationError(
            "preregistered contract and phase must be supplied together"
        )
    formal_binding: dict[str, Any] = {"status": "NOT_REQUESTED"}
    if preregistered_contract is not None and phase is not None:
        supplied_contract = Path(preregistered_contract).expanduser()
        if not supplied_contract.is_absolute():
            raise FormalBindingError("preregistered contract path must be absolute")
        formal_binding = _validate_formal_binding(
            contract_path=supplied_contract,
            phase=phase,
            child_argv=command,
            child_environment=child_env,
        )

    # All binding, dependency, and destination checks happen before creating
    # even the wrapper's own evidence directory.  A rejected formal run must
    # therefore leave no misleading partial run behind.
    planned_attest_files, planned_attest_trees = _prepare_attestation_targets(
        attest_files, attest_trees
    )
    prior_status_results = _verify_prior_statuses(
        require_prior_statuses, formal_binding=formal_binding
    )
    attestation_requested = bool(planned_attest_files or planned_attest_trees)
    attestation: dict[str, Any] = {
        "status": "PENDING" if attestation_requested else "NOT_REQUESTED",
        "requested_files": [str(path) for path in planned_attest_files],
        "requested_trees": [str(path) for path in planned_attest_trees],
        "files": [],
        "trees": [],
        "bundle_sha256": None,
        "verified_at_utc": None,
        "error": None,
    }

    resource_path = Path(resource_log).expanduser().resolve(strict=False)
    status = Path(status_path).expanduser().resolve(strict=False)
    disk_target = Path(disk_path).expanduser().resolve(strict=False)
    if not disk_target.exists():
        raise ConfigurationError(f"disk path does not exist: {disk_target}")
    stdout_path, stderr_path = _derived_log_paths(status)
    evidence_paths = {resource_path, status, stdout_path, stderr_path}
    target_collisions = evidence_paths & set(
        planned_attest_files + planned_attest_trees
    )
    tree_evidence_collisions = {
        evidence
        for tree in planned_attest_trees
        for evidence in evidence_paths
        if tree in evidence.parents
    }
    target_collisions.update(tree_evidence_collisions)
    if target_collisions:
        raise ConfigurationError(
            "attestation targets must differ from wrapper evidence paths: "
            + ", ".join(str(path) for path in sorted(target_collisions))
        )
    _reserve_output_paths((resource_path, status, stdout_path, stderr_path))

    wrapper_started_at = _utc_now()
    wrapper_started_monotonic = time.monotonic()
    command_started_at: str | None = None
    command_started_monotonic: float | None = None
    command_ended_at: str | None = None
    command_ended_monotonic: float | None = None
    disk_observations: list[ProbeResult] = []
    rss_observations: list[ProbeResult] = []
    swap_observations: list[ProbeResult] = []
    disk_minimum: int | None = None
    rss_peak: int | None = None
    rss_max_process_count = 0
    swap_peak_growth: int | None = None
    samples_count = 0
    resource_poll_count = 0
    heartbeat_count = 0
    process: subprocess.Popen[bytes] | None = None
    exit_code: int | None = None
    trigger: str | None = None
    verdict: str | None = None
    command_outcome = "NOT_STARTED"
    process_group_signalled = False
    escalated_to_sigkill = False
    external_signal: int | None = None
    launch_error: str | None = None

    # Exclusive opens make the earlier collision check race-safe.
    with (
        resource_path.open("x", encoding="utf-8") as sample_stream,
        stdout_path.open("xb") as stdout_stream,
        stderr_path.open("xb") as stderr_stream,
    ):
        disk_start = _safe_probe(disk_probe, disk_target)
        swap_start = _safe_probe(swap_probe)
        disk_observations.append(disk_start)
        swap_observations.append(swap_start)
        if disk_start.value_bytes is not None:
            disk_minimum = disk_start.value_bytes
        if swap_start.value_bytes is not None:
            swap_peak_growth = 0

        preflight_sample = {
            "schema_version": SCHEMA_VERSION,
            "sequence": samples_count,
            "phase": "preflight",
            "timestamp_utc": _utc_now(),
            "elapsed_seconds": time.monotonic() - wrapper_started_monotonic,
            "disk": disk_start.as_json(),
            "rss": ProbeResult.unknown("process not started").as_json(),
            "swap": swap_start.as_json(),
            "label": label,
            "command": {
                "argv": command,
                "shell": False,
                "canonical_sha256": _canonical_sha256(command),
            },
            "environment": {
                "allowlist": allowlist,
                "effective": child_env,
                "canonical_sha256": _canonical_sha256(child_env),
            },
            "thresholds": {
                "start_available_bytes": start_limit,
                "stop_available_bytes": stop_limit,
                "peak_rss_bytes": rss_limit,
                "swap_growth_bytes": swap_limit,
                "wall_timeout_seconds": timeout,
                "sample_interval_seconds": interval,
                "resource_poll_seconds": resource_poll,
            },
            "formal_binding": formal_binding,
            "attestation": attestation,
            "prior_statuses": prior_status_results,
        }
        _append_sample(sample_stream, preflight_sample)
        samples_count += 1

        if disk_start.status != "KNOWN":
            verdict = "UNKNOWN"
            trigger = "disk_preflight_unknown"
        elif disk_start.value_bytes is not None and disk_start.value_bytes < start_limit:
            verdict = "DISK_GUARD"
            trigger = "disk_preflight_limit"

        original_handlers: dict[int, Any] = {}

        def handle_signal(signum: int, _frame: Any) -> None:
            nonlocal external_signal, process_group_signalled, escalated_to_sigkill
            external_signal = signum
            if process is not None:
                signalled, escalated = _terminate_process_group(
                    process, grace_seconds=grace
                )
                process_group_signalled = process_group_signalled or signalled
                escalated_to_sigkill = escalated_to_sigkill or escalated

        can_install_handlers = threading.current_thread() is threading.main_thread()
        if can_install_handlers:
            for signum in (
                signal.SIGINT,
                signal.SIGTERM,
                signal.SIGHUP,
                signal.SIGQUIT,
            ):
                original_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, handle_signal)

        try:
            if verdict is None:
                try:
                    command_started_at = _utc_now()
                    command_started_monotonic = time.monotonic()
                    process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=stdout_stream,
                        stderr=stderr_stream,
                        env=child_env,
                        start_new_session=True,
                    )
                    command_outcome = "RUNNING"
                except OSError as exc:
                    command_started_at = None
                    command_started_monotonic = None
                    launch_error = f"{type(exc).__name__}: {exc}"
                    verdict = "LAUNCH_ERROR"
                    trigger = "launch_error"

            last_disk = disk_start
            last_rss = ProbeResult.unknown("process has not been polled")
            last_swap = swap_start
            last_rss_status: str | None = None
            last_swap_status: str | None = swap_start.status
            next_resource_due = command_started_monotonic or math.inf
            next_heartbeat_due = command_started_monotonic or math.inf
            first_process_sample = True
            while process is not None and (
                first_process_sample or process.poll() is None
            ):
                sample_started_monotonic = time.monotonic()
                if command_started_monotonic is None:
                    raise AssertionError("launched process lacks a monotonic start")
                elapsed = sample_started_monotonic - command_started_monotonic
                resource_due = (
                    first_process_sample
                    or sample_started_monotonic >= next_resource_due
                )
                heartbeat_due = (
                    first_process_sample
                    or sample_started_monotonic >= next_heartbeat_due
                )
                first_process_sample = False
                resource_changed = False

                # Disk is the heartbeat clock.  Probe it first when both
                # cadences are due so RSS/sysctl latency cannot systematically
                # push a 30-minute disk observation beyond its deadline.
                if heartbeat_due:
                    disk_now = _safe_probe(disk_probe, disk_target)
                    disk_observations.append(disk_now)
                    heartbeat_count += 1
                    last_disk = disk_now
                    next_heartbeat_due = sample_started_monotonic + interval

                if resource_due:
                    rss_now = _safe_probe(rss_probe, process.pid)
                    swap_now = _safe_probe(swap_probe)
                    rss_observations.append(rss_now)
                    swap_observations.append(swap_now)
                    resource_poll_count += 1

                    previous_rss_peak = rss_peak
                    previous_swap_peak = swap_peak_growth
                    if rss_now.value_bytes is not None:
                        rss_peak = (
                            rss_now.value_bytes
                            if rss_peak is None
                            else max(rss_peak, rss_now.value_bytes)
                        )
                        rss_max_process_count = max(
                            rss_max_process_count,
                            int(rss_now.details.get("process_count", 0)),
                        )
                    if (
                        swap_start.value_bytes is not None
                        and swap_now.value_bytes is not None
                    ):
                        growth = max(
                            0, swap_now.value_bytes - swap_start.value_bytes
                        )
                        swap_peak_growth = (
                            growth
                            if swap_peak_growth is None
                            else max(swap_peak_growth, growth)
                        )
                    resource_changed = (
                        rss_now.status != last_rss_status
                        or swap_now.status != last_swap_status
                        or rss_peak != previous_rss_peak
                        or swap_peak_growth != previous_swap_peak
                    )
                    last_rss = rss_now
                    last_swap = swap_now
                    last_rss_status = rss_now.status
                    last_swap_status = swap_now.status
                    next_resource_due = sample_started_monotonic + resource_poll

                if heartbeat_due and last_disk.value_bytes is not None:
                    disk_minimum = (
                        last_disk.value_bytes
                        if disk_minimum is None
                        else min(disk_minimum, last_disk.value_bytes)
                    )

                if external_signal is not None:
                    verdict = "INTERRUPTED"
                    trigger = "external_signal"
                elif (
                    last_disk.value_bytes is not None
                    and last_disk.value_bytes < stop_limit
                ):
                    verdict = "DISK_GUARD"
                    trigger = "disk_limit"
                elif (
                    last_rss.value_bytes is not None
                    and last_rss.value_bytes > rss_limit
                ):
                    verdict = "RESOURCE_GUARD"
                    trigger = "rss_limit"
                elif (
                    swap_start.value_bytes is not None
                    and last_swap.value_bytes is not None
                    and last_swap.value_bytes - swap_start.value_bytes > swap_limit
                ):
                    verdict = "RESOURCE_GUARD"
                    trigger = "swap_growth_limit"
                elif elapsed >= timeout:
                    verdict = "TIMEOUT"
                    trigger = "wall_timeout"

                if heartbeat_due or resource_changed or verdict is not None:
                    phase = (
                        "guard"
                        if verdict is not None
                        else "heartbeat"
                        if heartbeat_due
                        else "resource_change"
                    )
                    sample = {
                        "schema_version": SCHEMA_VERSION,
                        "sequence": samples_count,
                        "phase": phase,
                        "timestamp_utc": _utc_now(),
                        "elapsed_seconds": elapsed,
                        "pid": process.pid,
                        "disk_sampled": heartbeat_due,
                        "resource_polled": resource_due,
                        "resource_poll_count": resource_poll_count,
                        "heartbeat_count": heartbeat_count,
                        "disk": last_disk.as_json(),
                        "rss": last_rss.as_json(),
                        "swap": last_swap.as_json(),
                        "swap_growth_bytes": (
                            None
                            if swap_start.value_bytes is None
                            or last_swap.value_bytes is None
                            else max(
                                0,
                                last_swap.value_bytes - swap_start.value_bytes,
                            )
                        ),
                        "trigger": trigger,
                    }
                    _append_sample(sample_stream, sample)
                    samples_count += 1

                if verdict is not None:
                    signalled, escalated = _terminate_process_group(
                        process, grace_seconds=grace
                    )
                    process_group_signalled = process_group_signalled or signalled
                    escalated_to_sigkill = escalated_to_sigkill or escalated
                    break

                next_timeout_due = command_started_monotonic + timeout
                next_wake = min(
                    next_resource_due,
                    next_heartbeat_due,
                    next_timeout_due,
                )
                remaining = next_wake - time.monotonic()
                if remaining <= 0:
                    continue
                try:
                    process.wait(timeout=remaining)
                except subprocess.TimeoutExpired:
                    pass

            if process is not None:
                try:
                    exit_code = process.wait(timeout=max(1.0, grace))
                except subprocess.TimeoutExpired:
                    signalled, escalated = _terminate_process_group(
                        process, grace_seconds=grace
                    )
                    process_group_signalled = process_group_signalled or signalled
                    escalated_to_sigkill = escalated_to_sigkill or escalated
                    exit_code = process.poll()
                if external_signal is not None and verdict is None:
                    verdict = "INTERRUPTED"
                    trigger = "external_signal"
                command_outcome = "SUCCESS" if exit_code == 0 else "FAILED"

                # A launcher is not allowed to leave work behind outside the
                # wrapper's accounting window.  Descendants retain the new
                # process group even after the direct child exits.
                lingering_group = _process_group_exists(process.pid)
                if lingering_group:
                    signalled, escalated = _terminate_process_group(
                        process, grace_seconds=grace
                    )
                    process_group_signalled = process_group_signalled or signalled
                    escalated_to_sigkill = escalated_to_sigkill or escalated
                    if verdict is None:
                        verdict = "RESOURCE_GUARD"
                        trigger = "descendants_outlived_command"
                command_ended_monotonic = time.monotonic()
                command_ended_at = _utc_now()
        finally:
            if process is not None and process.poll() is None:
                signalled, escalated = _terminate_process_group(
                    process, grace_seconds=grace
                )
                process_group_signalled = process_group_signalled or signalled
                escalated_to_sigkill = escalated_to_sigkill or escalated
                exit_code = process.poll()
                command_outcome = "SUCCESS" if exit_code == 0 else "FAILED"
            if process is not None and command_ended_monotonic is None:
                command_ended_monotonic = time.monotonic()
                command_ended_at = _utc_now()
            if can_install_handlers:
                for signum, handler in original_handlers.items():
                    signal.signal(signum, handler)

        if attestation_requested:
            if verdict is None and command_outcome == "SUCCESS":
                try:
                    verified_attestation = _attest_outputs(
                        planned_attest_files, planned_attest_trees
                    )
                except AttestationError as exc:
                    attestation.update(
                        {
                            "status": "FAILED",
                            "files": [],
                            "trees": [],
                            "bundle_sha256": None,
                            "verified_at_utc": None,
                            "error": str(exc),
                        }
                    )
                    verdict = "ATTESTATION_FAILED"
                    trigger = "attestation_failed"
                else:
                    attestation.update(verified_attestation)
            elif verdict is None and command_outcome == "FAILED":
                attestation["status"] = "SKIPPED_CHILD_FAILED"
            else:
                attestation["status"] = "SKIPPED_NON_SUCCESS"

        disk_end = _safe_probe(disk_probe, disk_target)
        swap_end = _safe_probe(swap_probe)
        disk_observations.append(disk_end)
        swap_observations.append(swap_end)
        if disk_end.value_bytes is not None:
            disk_minimum = (
                disk_end.value_bytes
                if disk_minimum is None
                else min(disk_minimum, disk_end.value_bytes)
            )
        if swap_start.value_bytes is not None and swap_end.value_bytes is not None:
            growth = max(0, swap_end.value_bytes - swap_start.value_bytes)
            swap_peak_growth = (
                growth if swap_peak_growth is None else max(swap_peak_growth, growth)
            )
        end_sample = {
            "schema_version": SCHEMA_VERSION,
            "sequence": samples_count,
            "phase": "end",
            "timestamp_utc": _utc_now(),
            "elapsed_seconds": (
                None
                if command_started_monotonic is None
                else (command_ended_monotonic or time.monotonic())
                - command_started_monotonic
            ),
            "pid": None if process is None else process.pid,
            "disk": disk_end.as_json(),
            "rss": ProbeResult.known(0, details={"process_count": 0}).as_json(),
            "swap": swap_end.as_json(),
            "swap_growth_bytes": (
                None
                if swap_start.value_bytes is None or swap_end.value_bytes is None
                else max(0, swap_end.value_bytes - swap_start.value_bytes)
            ),
            "resource_poll_count": resource_poll_count,
            "heartbeat_count": heartbeat_count,
        }
        _append_sample(sample_stream, end_sample)
        samples_count += 1

    wrapper_ended_at = _utc_now()
    wrapper_wall_seconds = time.monotonic() - wrapper_started_monotonic
    wall_seconds = (
        None
        if command_started_monotonic is None or command_ended_monotonic is None
        else command_ended_monotonic - command_started_monotonic
    )
    disk_summary = _metric_summary(
        observations=disk_observations,
        start_value=disk_start.value_bytes,
        end_value=disk_end.value_bytes,
        minimum_value=disk_minimum,
    )
    rss_summary = _metric_summary(
        observations=rss_observations,
        start_value=rss_observations[0].value_bytes if rss_observations else None,
        end_value=rss_observations[-1].value_bytes if rss_observations else None,
        peak_value=rss_peak,
    )
    rss_summary["max_process_count"] = rss_max_process_count
    rss_summary["measurement"] = "high_frequency_sampled_ps_descendant_rss_sum"
    rss_summary["observation_count"] = len(rss_observations)
    rss_summary["poll_interval_seconds"] = resource_poll
    swap_summary = _metric_summary(
        observations=swap_observations,
        start_value=swap_start.value_bytes,
        end_value=swap_end.value_bytes,
        peak_growth=swap_peak_growth,
    )
    swap_summary["measurement"] = "high_frequency_sampled_sysctl_swap_growth"
    swap_summary["observation_count"] = len(swap_observations)
    swap_summary["poll_interval_seconds"] = resource_poll
    disk_summary["measurement"] = "heartbeat_filesystem_available_bytes"
    disk_summary["observation_count"] = len(disk_observations)
    disk_summary["heartbeat_interval_seconds"] = interval

    # A limit crossed in the final observation is still a guarded run even
    # when the command happened to exit between samples.  Known guard evidence
    # takes precedence over unrelated unknown telemetry.
    if verdict is None and disk_minimum is not None and disk_minimum < stop_limit:
        verdict = "DISK_GUARD"
        trigger = "disk_limit_at_end"
    if (
        verdict is None
        and swap_peak_growth is not None
        and swap_peak_growth > swap_limit
    ):
        verdict = "RESOURCE_GUARD"
        trigger = "swap_growth_limit_at_end"

    if verdict is None:
        if command_outcome != "SUCCESS":
            verdict = "COMMAND_FAILED"
        elif any(
            summary["status"] == "UNKNOWN"
            for summary in (disk_summary, rss_summary, swap_summary)
        ):
            verdict = "UNKNOWN"
            trigger = "resource_telemetry_unknown"
        else:
            verdict = "PASS"

    stdout_size = stdout_path.stat().st_size
    stderr_size = stderr_path.stat().st_size
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "label": label,
        "verdict": verdict,
        "command_outcome": command_outcome,
        "started": process is not None,
        "exit_code": exit_code,
        "command": {
            "argv": command,
            "shell": False,
            "canonical_sha256": _canonical_sha256(command),
        },
        "formal_binding": formal_binding,
        "attestation": attestation,
        "prior_statuses": prior_status_results,
        "environment": {
            "allowlist": allowlist,
            "effective": child_env,
            "canonical_sha256": _canonical_sha256(child_env),
        },
        "timing": {
            "wrapper_started_at_utc": wrapper_started_at,
            "wrapper_ended_at_utc": wrapper_ended_at,
            "command_started_at_utc": command_started_at,
            "command_ended_at_utc": command_ended_at,
            "wall_seconds": wall_seconds,
            "wrapper_wall_seconds": wrapper_wall_seconds,
            "wall_timeout_seconds": timeout,
            "sample_interval_seconds": interval,
            "resource_poll_seconds": resource_poll,
        },
        "wall_seconds": wall_seconds,
        "thresholds": {
            "start_available_bytes": start_limit,
            "stop_available_bytes": stop_limit,
            "peak_rss_bytes": rss_limit,
            "swap_growth_bytes": swap_limit,
        },
        "disk_path": str(disk_target),
        "samples_count": samples_count,
        "resource_poll_count": resource_poll_count,
        "heartbeat_count": heartbeat_count,
        "resources": {
            "disk": disk_summary,
            "rss": rss_summary,
            "swap": swap_summary,
        },
        "termination": {
            "trigger": trigger,
            "process_group_signalled": process_group_signalled,
            "escalated_to_sigkill": escalated_to_sigkill,
            "external_signal": external_signal,
            "process_group_alive_at_status": (
                False if process is None else _process_group_exists(process.pid)
            ),
        },
        "launch_error": launch_error,
        "logs": {
            "resources": {
                "path": str(resource_path),
                "bytes": resource_path.stat().st_size,
                "sha256": _sha256_file(resource_path),
            },
            "stdout": {
                "path": str(stdout_path),
                "bytes": stdout_size,
                "sha256": _sha256_file(stdout_path),
            },
            "stderr": {
                "path": str(stderr_path),
                "bytes": stderr_size,
                "sha256": _sha256_file(stderr_path),
            },
        },
    }
    with status.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return result


def _parse_env_assignment(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise ConfigurationError(f"--env requires NAME=VALUE, got {raw!r}")
    name, value = raw.split("=", 1)
    if not _ENV_NAME_RE.fullmatch(name):
        raise ConfigurationError(f"invalid environment name: {name!r}")
    return name, value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--resource-log", type=Path, required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--disk-path", type=Path, required=True)
    parser.add_argument("--start-available-gib", type=float, default=15.0)
    parser.add_argument("--stop-available-gib", type=float, default=6.0)
    parser.add_argument(
        "--sample-interval-seconds",
        type=float,
        default=1800.0,
        help="disk/evidence heartbeat cadence; must be <= 1800 seconds",
    )
    parser.add_argument(
        "--resource-poll-seconds",
        type=float,
        default=1.0,
        help="RSS/swap guard cadence; must be <= min(5 seconds, heartbeat)",
    )
    parser.add_argument("--peak-rss-gib", type=float, default=12.0)
    parser.add_argument("--swap-growth-gib", type=float, default=4.0)
    parser.add_argument("--wall-time-seconds", type=float, default=14400.0)
    parser.add_argument(
        "--preregistered-contract",
        type=Path,
        help="absolute b0-preregistration-v1 contract for a formal bound run",
    )
    parser.add_argument(
        "--phase",
        help="key in execution_plan.formal_runner_bindings; requires contract",
    )
    parser.add_argument(
        "--attest-file",
        action="append",
        type=Path,
        default=[],
        metavar="ABS",
        help="new regular file to hash after a successful child exit; repeatable",
    )
    parser.add_argument(
        "--attest-tree",
        action="append",
        type=Path,
        default=[],
        metavar="ABS",
        help="new directory tree to hash after a successful child exit; repeatable",
    )
    parser.add_argument(
        "--require-prior-status",
        action="append",
        type=Path,
        default=[],
        metavar="ABS",
        help="PASS status whose attested artifacts must still match; repeatable",
    )
    parser.add_argument(
        "--allow-env",
        action="append",
        default=[],
        metavar="NAME",
        help="add a parent environment variable to the fixed default allowlist",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="set and record an explicit child environment value",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def _gib_to_bytes(value: float, *, label: str) -> int:
    amount = _validate_positive_finite(value, label=label)
    return int(amount * GIB)


def validate_cli_args(args: argparse.Namespace) -> tuple[list[str], dict[str, str]]:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise ConfigurationError("missing command after --")
    _validate_positive_finite(args.sample_interval_seconds, label="sample interval")
    if args.sample_interval_seconds > MAX_SAMPLE_INTERVAL_SECONDS:
        raise ConfigurationError("sample interval must be <= 1800 seconds")
    resource_poll = _validate_positive_finite(
        args.resource_poll_seconds, label="resource poll interval"
    )
    if resource_poll > min(MAX_RESOURCE_POLL_SECONDS, args.sample_interval_seconds):
        raise ConfigurationError(
            "resource poll interval must be <= min(5 seconds, sample interval)"
        )
    if (args.preregistered_contract is None) != (args.phase is None):
        raise ConfigurationError(
            "preregistered contract and phase must be supplied together"
        )
    if args.preregistered_contract is not None:
        if not args.preregistered_contract.expanduser().is_absolute():
            raise ConfigurationError("preregistered contract path must be absolute")
        if not isinstance(args.phase, str) or not _PHASE_RE.fullmatch(args.phase):
            raise ConfigurationError(f"invalid formal phase key: {args.phase!r}")
    for option, values in (
        ("--attest-file", args.attest_file),
        ("--attest-tree", args.attest_tree),
        ("--require-prior-status", args.require_prior_status),
    ):
        for value in values:
            _canonical_absolute_path(value, label=option)
    _validate_positive_finite(args.wall_time_seconds, label="wall timeout")
    overrides = dict(_parse_env_assignment(raw) for raw in args.env)
    return command, overrides


def _exit_status(result: Mapping[str, Any]) -> int:
    verdict = result.get("verdict")
    if verdict == "PASS":
        return 0
    if verdict == "TIMEOUT":
        return 124
    if verdict == "DISK_GUARD":
        return 75
    if verdict == "RESOURCE_GUARD":
        return 76
    if verdict == "ATTESTATION_FAILED":
        return 77
    if verdict == "INTERRUPTED":
        signum = result.get("termination", {}).get("external_signal")
        return 128 + int(signum or signal.SIGTERM)
    if verdict == "COMMAND_FAILED":
        code = result.get("exit_code")
        if isinstance(code, int) and 1 <= code <= 125:
            return code
        if isinstance(code, int) and code < 0:
            return min(255, 128 + abs(code))
        return 1
    if verdict == "LAUNCH_ERROR":
        return 127
    return 3


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        command, overrides = validate_cli_args(args)
        allowlist = tuple(DEFAULT_ENV_ALLOWLIST) + tuple(args.allow_env)
        result = run_monitored(
            command,
            resource_log=args.resource_log,
            status_path=args.status,
            disk_path=args.disk_path,
            label=args.label,
            env_allowlist=allowlist,
            env_overrides=overrides,
            start_available_bytes=_gib_to_bytes(
                args.start_available_gib, label="start available GiB"
            ),
            stop_available_bytes=_gib_to_bytes(
                args.stop_available_gib, label="stop available GiB"
            ),
            sample_interval_seconds=args.sample_interval_seconds,
            resource_poll_seconds=args.resource_poll_seconds,
            peak_rss_bytes=_gib_to_bytes(args.peak_rss_gib, label="peak RSS GiB"),
            swap_growth_bytes=_gib_to_bytes(
                args.swap_growth_gib, label="swap growth GiB"
            ),
            wall_timeout_seconds=args.wall_time_seconds,
            preregistered_contract=args.preregistered_contract,
            phase=args.phase,
            attest_files=args.attest_file,
            attest_trees=args.attest_tree,
            require_prior_statuses=args.require_prior_status,
        )
    except (ConfigurationError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": str(args.status), "verdict": result["verdict"]}))
    return _exit_status(result)


if __name__ == "__main__":
    raise SystemExit(main())
