#!/usr/bin/env python3
"""Evaluate the controlled incremental-global-BA OFF/ON experiment.

The evaluator is deliberately configuration driven.  It does not contain
product thresholds: all nine registered gates must be present in the supplied
evaluation config.  Each arm is a self-contained evidence directory with a run
config, a SHA-256 manifest, one selected PLY, and one selected NPZ archive.

Exit codes:
    0  all nine gates pass
    1  complete evidence, at least one gate fails
    2  invalid evidence or the OFF/ON single-variable contract is violated
    3  evidence or a registered threshold is missing
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import inspect
import json
import math
import os
import re
import stat
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any


SCHEMA_VERSION = "aether_incremental_ba_ab_verdict_v1"
CONTROL_VARIABLE = "AETHER_INCREMENTAL_GLOBAL_BA"
GATE_IDS = (
    "reprojection",
    "registered_frames",
    "sparse_points",
    "floor_thickness",
    "ghost_layers",
    "wall_ceiling_coverage",
    "wrong_acceptance",
    "peak_memory",
    "runtime",
)
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class EvaluationError(RuntimeError):
    """Base class for an evidence-closed evaluator error."""


class InvalidEvidenceError(EvaluationError):
    """Evidence is present but malformed, unsafe, or contradictory."""


class ControlVariableError(InvalidEvidenceError):
    """OFF and ON are not a strict single-variable experiment."""


class InsufficientEvidenceError(EvaluationError):
    """Required evidence is absent, so no pass/fail claim is possible."""


@dataclass(frozen=True)
class FileIdentity:
    path: Path
    sha256: str
    bytes: int

    def as_json(self, *, relative_to: Path | None = None) -> dict[str, Any]:
        path = self.path
        if relative_to is not None:
            try:
                display_path = path.relative_to(relative_to).as_posix()
            except ValueError:
                display_path = str(path)
        else:
            display_path = str(path)
        return {"path": display_path, "sha256": self.sha256, "bytes": self.bytes}


@dataclass(frozen=True)
class ArmEvidence:
    name: str
    directory: Path
    run_config_path: Path
    hash_manifest_path: Path
    ply_path: Path
    npz_path: Path
    run_config: dict[str, Any]
    identities: dict[str, FileIdentity]
    ply_info: dict[str, Any]
    npz_info: dict[str, Any]
    npz_scalars: dict[str, Any]


def _reject_constant(value: str) -> None:
    raise InvalidEvidenceError(f"non-finite JSON token is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidEvidenceError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _check_finite_json(value: Any, pointer: str = "") -> None:
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidEvidenceError(f"non-finite JSON number at {pointer or '/'}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_finite_json(item, f"{pointer}/{index}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            _check_finite_json(item, f"{pointer}/{escaped}")
        return
    raise InvalidEvidenceError(
        f"unsupported JSON value {type(value).__name__} at {pointer or '/'}"
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InsufficientEvidenceError(f"missing JSON file: {path}") from exc
    except OSError as exc:
        raise InvalidEvidenceError(f"cannot read JSON file {path}: {exc}") from exc
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except EvaluationError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidEvidenceError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InvalidEvidenceError(f"JSON root must be an object: {path}")
    _check_finite_json(value)
    return value


def hash_regular_file(path: Path) -> FileIdentity:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError as exc:
        raise InsufficientEvidenceError(f"missing evidence file: {path}") from exc
    except OSError as exc:
        raise InvalidEvidenceError(f"cannot open evidence file {path}: {exc}") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise InvalidEvidenceError(f"evidence is not a regular file: {path}")
        digest = hashlib.sha256()
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    mutation_fields = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    after_fields = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if mutation_fields != after_fields:
        raise InvalidEvidenceError(f"evidence mutated while hashing: {path}")
    return FileIdentity(path=path, sha256=digest.hexdigest(), bytes=before.st_size)


def _ensure_inside(root: Path, candidate: Path, *, label: str) -> Path:
    try:
        root_resolved = root.resolve(strict=True)
    except FileNotFoundError as exc:
        raise InsufficientEvidenceError(f"missing arm directory: {root}") from exc
    if not root_resolved.is_dir():
        raise InvalidEvidenceError(f"arm directory is not a directory: {root}")
    lexical = candidate if candidate.is_absolute() else root / candidate
    current = Path(lexical.anchor) if lexical.is_absolute() else Path()
    for part in lexical.parts[1:] if lexical.is_absolute() else lexical.parts:
        current = current / part
        if current.is_symlink():
            raise InvalidEvidenceError(f"{label} traverses a symlink: {current}")
    try:
        resolved = lexical.resolve(strict=True)
    except FileNotFoundError as exc:
        raise InsufficientEvidenceError(f"missing {label}: {lexical}") from exc
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise InvalidEvidenceError(f"{label} escapes arm directory: {lexical}") from exc
    if not resolved.is_file():
        raise InvalidEvidenceError(f"{label} is not a regular file: {resolved}")
    return resolved


def _arm_section(config: Mapping[str, Any], arm: str) -> Mapping[str, Any]:
    arms = config.get("arms")
    if not isinstance(arms, Mapping):
        return {}
    for key, value in arms.items():
        if str(key).lower() == arm and isinstance(value, Mapping):
            return value
    return {}


ARTIFACT_ALIASES: dict[str, tuple[str, ...]] = {
    "run_config": ("run_config", "config", "effective_config"),
    "hash_manifest": ("hash_manifest", "hashes", "sha256_manifest"),
    "ply": ("ply", "cloud", "point_cloud"),
    "npz": ("npz", "metrics_npz", "telemetry_npz"),
}


def _configured_artifact(
    evaluation_config: Mapping[str, Any], arm: str, kind: str
) -> str | None:
    aliases = ARTIFACT_ALIASES[kind]
    containers: list[Mapping[str, Any]] = []
    section = _arm_section(evaluation_config, arm)
    if section:
        nested = section.get("artifacts")
        if isinstance(nested, Mapping):
            containers.append(nested)
        containers.append(section)
    shared = evaluation_config.get("artifacts")
    if isinstance(shared, Mapping):
        containers.append(shared)
    files = evaluation_config.get("files")
    if isinstance(files, Mapping):
        containers.append(files)
    for container in containers:
        for alias in aliases:
            value = container.get(alias)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, Mapping):
                nested_path = value.get("path")
                if isinstance(nested_path, str) and nested_path:
                    return nested_path
    return None


AUTODETECT_NAMES: dict[str, tuple[str, ...]] = {
    "run_config": ("config.json", "run_config.json", "effective_config.json"),
    "hash_manifest": (
        "hashes.json",
        "sha256.json",
        "SHA256SUMS",
        "hashes.sha256",
    ),
}


def _autodetect_artifact(root: Path, kind: str) -> Path:
    if kind in AUTODETECT_NAMES:
        matches = [root / name for name in AUTODETECT_NAMES[kind] if (root / name).is_file()]
    else:
        suffix = ".ply" if kind == "ply" else ".npz"
        matches = sorted(path for path in root.rglob(f"*{suffix}") if path.is_file())
    if not matches:
        raise InsufficientEvidenceError(f"no {kind} evidence found in {root}")
    if len(matches) != 1:
        rendered = ", ".join(str(path.relative_to(root)) for path in matches)
        raise InvalidEvidenceError(
            f"ambiguous {kind} evidence in {root}; configure one path explicitly: {rendered}"
        )
    return matches[0]


def _resolve_artifact(
    root: Path,
    evaluation_config: Mapping[str, Any],
    arm: str,
    kind: str,
    cli_value: str | None,
) -> Path:
    selected = cli_value or _configured_artifact(evaluation_config, arm, kind)
    candidate = Path(selected) if selected else _autodetect_artifact(root, kind)
    return _ensure_inside(root, candidate, label=f"{arm} {kind}")


def _normal_manifest_path(value: str) -> str:
    if "\\" in value:
        raise InvalidEvidenceError(f"hash manifest path uses a backslash: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise InvalidEvidenceError(f"unsafe hash manifest path: {value!r}")
    return pure.as_posix()


def _add_manifest_entry(entries: dict[str, str], path: Any, digest: Any) -> None:
    if not isinstance(path, str) or not isinstance(digest, str):
        return
    if not SHA256_RE.fullmatch(digest):
        return
    normalized = _normal_manifest_path(path)
    digest = digest.lower()
    old = entries.get(normalized)
    if old is not None and old != digest:
        raise InvalidEvidenceError(f"conflicting hashes for {normalized}")
    entries[normalized] = digest


def _collect_json_manifest_entries(value: Any, entries: dict[str, str]) -> None:
    if isinstance(value, Mapping):
        _add_manifest_entry(entries, value.get("path"), value.get("sha256"))
        for key, child in value.items():
            if isinstance(child, str):
                _add_manifest_entry(entries, key, child)
            else:
                _collect_json_manifest_entries(child, entries)
    elif isinstance(value, list):
        for child in value:
            _collect_json_manifest_entries(child, entries)


def load_hash_manifest(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise InsufficientEvidenceError(f"missing hash manifest: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise InvalidEvidenceError(f"cannot read hash manifest {path}: {exc}") from exc
    entries: dict[str, str] = {}
    if path.suffix.lower() == ".json" or text.lstrip().startswith(("{", "[")):
        try:
            value = json.loads(
                text,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except EvaluationError:
            raise
        except json.JSONDecodeError as exc:
            raise InvalidEvidenceError(f"invalid hash manifest JSON {path}: {exc}") from exc
        _collect_json_manifest_entries(value, entries)
    else:
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.fullmatch(r"([0-9a-fA-F]{64})\s+[* ]?(.+?)\s*", line)
            if match is None:
                raise InvalidEvidenceError(
                    f"invalid hash manifest line {path}:{line_number}: {raw_line!r}"
                )
            _add_manifest_entry(entries, match.group(2), match.group(1))
    if not entries:
        raise InsufficientEvidenceError(f"hash manifest has no SHA-256 entries: {path}")
    return entries


def verify_hash_manifest(
    root: Path,
    manifest_path: Path,
    required_paths: Sequence[Path],
) -> tuple[dict[str, FileIdentity], int]:
    entries = load_hash_manifest(manifest_path)
    root = root.resolve(strict=True)
    required_rel = {path.relative_to(root).as_posix() for path in required_paths}
    missing = sorted(required_rel - set(entries))
    if missing:
        raise InsufficientEvidenceError(
            f"hash manifest {manifest_path} does not cover required evidence: "
            + ", ".join(missing)
        )
    identities: dict[str, FileIdentity] = {}
    for relative, expected in sorted(entries.items()):
        evidence_path = _ensure_inside(root, Path(relative), label="hashed evidence")
        identity = hash_regular_file(evidence_path)
        if identity.sha256 != expected:
            raise InvalidEvidenceError(
                f"SHA-256 mismatch for {relative}: expected {expected}, got {identity.sha256}"
            )
        identities[relative] = identity
    return identities, len(entries)


def inspect_ply(path: Path) -> dict[str, Any]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise InvalidEvidenceError(f"cannot inspect PLY {path}: {exc}") from exc
    try:
        data = bytearray()
        marker = b"end_header\n"
        while marker not in data:
            block = os.read(fd, 4096)
            if not block:
                break
            data.extend(block)
            if len(data) > 1024 * 1024:
                raise InvalidEvidenceError(f"PLY header exceeds 1 MiB: {path}")
    finally:
        os.close(fd)
    marker_index = data.find(marker)
    marker_size = len(marker)
    if marker_index < 0:
        marker = b"end_header\r\n"
        marker_index = data.find(marker)
        marker_size = len(marker)
    if marker_index < 0:
        raise InvalidEvidenceError(f"PLY has no complete end_header: {path}")
    header_bytes = bytes(data[: marker_index + marker_size])
    try:
        lines = header_bytes.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise InvalidEvidenceError(f"PLY header is not ASCII: {path}") from exc
    if not lines or lines[0].strip() != "ply":
        raise InvalidEvidenceError(f"not a PLY file: {path}")
    formats = [line.split() for line in lines if line.startswith("format ")]
    if len(formats) != 1 or len(formats[0]) < 3:
        raise InvalidEvidenceError(f"PLY must declare exactly one format: {path}")
    ply_format = formats[0][1]
    if ply_format not in ("ascii", "binary_little_endian", "binary_big_endian"):
        raise InvalidEvidenceError(f"unsupported PLY format {ply_format!r}: {path}")
    vertex_counts: list[int] = []
    for line in lines:
        fields = line.split()
        if len(fields) == 3 and fields[:2] == ["element", "vertex"]:
            try:
                count = int(fields[2])
            except ValueError as exc:
                raise InvalidEvidenceError(f"invalid PLY vertex count: {path}") from exc
            if count < 0:
                raise InvalidEvidenceError(f"negative PLY vertex count: {path}")
            vertex_counts.append(count)
    if len(vertex_counts) != 1:
        raise InvalidEvidenceError(f"PLY must declare exactly one vertex element: {path}")
    return {
        "format": ply_format,
        "version": formats[0][2],
        "vertex_count": vertex_counts[0],
        "header_bytes": len(header_bytes),
    }


def _python_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    return None


def inspect_npz(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        import numpy as np
    except ImportError as exc:
        raise InsufficientEvidenceError("NumPy is required to inspect NPZ evidence") from exc
    arrays: dict[str, Any] = {}
    scalars: dict[str, Any] = {}
    try:
        with np.load(path, allow_pickle=False) as archive:
            names = list(archive.files)
            if len(names) != len(set(names)):
                raise InvalidEvidenceError(f"NPZ contains duplicate array names: {path}")
            for name in names:
                try:
                    array = archive[name]
                except ValueError as exc:
                    raise InvalidEvidenceError(
                        f"NPZ array {name!r} cannot be loaded with allow_pickle=False: {path}"
                    ) from exc
                if array.dtype.hasobject:
                    raise InvalidEvidenceError(f"NPZ object dtype is forbidden: {path}:{name}")
                arrays[name] = {
                    "dtype": str(array.dtype),
                    "shape": [int(dimension) for dimension in array.shape],
                    "size": int(array.size),
                }
                if array.size == 1:
                    scalar = _python_scalar(array.reshape(-1)[0])
                    if scalar is not None:
                        scalars[name] = scalar
    except InvalidEvidenceError:
        raise
    except (OSError, ValueError) as exc:
        raise InvalidEvidenceError(f"invalid NPZ archive {path}: {exc}") from exc
    return {"array_count": len(arrays), "arrays": arrays}, scalars


def load_arm_evidence(
    name: str,
    directory: Path,
    evaluation_config: Mapping[str, Any],
    cli_paths: Mapping[str, str | None],
) -> ArmEvidence:
    directory = directory.resolve(strict=True)
    selected = {
        kind: _resolve_artifact(
            directory,
            evaluation_config,
            name,
            kind,
            cli_paths.get(kind),
        )
        for kind in ("run_config", "hash_manifest", "ply", "npz")
    }
    run_config = load_json(selected["run_config"])
    identities, manifest_count = verify_hash_manifest(
        directory,
        selected["hash_manifest"],
        (selected["run_config"], selected["ply"], selected["npz"]),
    )
    manifest_identity = hash_regular_file(selected["hash_manifest"])
    identities["__hash_manifest__"] = manifest_identity
    ply_info = inspect_ply(selected["ply"])
    npz_info, npz_scalars = inspect_npz(selected["npz"])
    npz_info["hash_manifest_entry_count"] = manifest_count
    return ArmEvidence(
        name=name,
        directory=directory,
        run_config_path=selected["run_config"],
        hash_manifest_path=selected["hash_manifest"],
        ply_path=selected["ply"],
        npz_path=selected["npz"],
        run_config=run_config,
        identities=identities,
        ply_info=ply_info,
        npz_info=npz_info,
        npz_scalars=npz_scalars,
    )


def _control_values(value: Any, pointer: str = "") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            child_pointer = f"{pointer}/{escaped}"
            if key == CONTROL_VARIABLE:
                found.append((child_pointer, child))
            found.extend(_control_values(child, child_pointer))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_control_values(child, f"{pointer}/{index}"))
    return found


def _remove_control(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _remove_control(child)
            for key, child in value.items()
            if key != CONTROL_VARIABLE
        }
    if isinstance(value, list):
        return [_remove_control(child) for child in value]
    return copy.deepcopy(value)


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _first_difference(left: Any, right: Any, pointer: str = "") -> str:
    if type(left) is not type(right):
        return pointer or "/"
    if isinstance(left, Mapping):
        left_keys = set(left)
        right_keys = set(right)
        if left_keys != right_keys:
            key = sorted(left_keys ^ right_keys, key=str)[0]
            return f"{pointer}/{key}"
        for key in sorted(left_keys, key=str):
            child = _first_difference(left[key], right[key], f"{pointer}/{key}")
            if child:
                return child
        return ""
    if isinstance(left, list):
        if len(left) != len(right):
            return pointer or "/"
        for index, (left_child, right_child) in enumerate(zip(left, right, strict=True)):
            child = _first_difference(left_child, right_child, f"{pointer}/{index}")
            if child:
                return child
        return ""
    return "" if left == right else (pointer or "/")


def _declared_control_name(config: Mapping[str, Any]) -> str | None:
    candidates: list[Any] = [config.get("control_variable")]
    experiment = config.get("experiment")
    if isinstance(experiment, Mapping):
        candidates.append(experiment.get("control_variable"))
    for value in candidates:
        if isinstance(value, str):
            return value
        if isinstance(value, Mapping) and isinstance(value.get("name"), str):
            return str(value["name"])
    return None


def validate_control_variable(
    off_config: Mapping[str, Any],
    on_config: Mapping[str, Any],
    evaluation_config: Mapping[str, Any],
) -> dict[str, Any]:
    declared = _declared_control_name(evaluation_config)
    if declared is not None and declared != CONTROL_VARIABLE:
        raise ControlVariableError(
            f"evaluation config declares {declared!r}; required {CONTROL_VARIABLE!r}"
        )
    off_values = _control_values(off_config)
    on_values = _control_values(on_config)
    if len(off_values) > 1 or len(on_values) != 1:
        raise ControlVariableError(
            f"expected at most one OFF and exactly one ON {CONTROL_VARIABLE} entry; "
            f"found OFF={len(off_values)}, ON={len(on_values)}"
        )
    if off_values:
        off_value = off_values[0][1]
        off_is_unset = off_value is None or (
            isinstance(off_value, str)
            and off_value.strip().lower() in {"unset", "(unset)", "absent"}
        )
        if not off_is_unset:
            raise ControlVariableError(
                f"OFF must leave {CONTROL_VARIABLE} unset, got {off_value!r}"
            )
    else:
        off_value = "unset"
    on_value = on_values[0][1]
    if isinstance(on_value, bool) or not (
        on_value == 1 or (isinstance(on_value, str) and on_value.strip() == "1")
    ):
        raise ControlVariableError(f"ON must set {CONTROL_VARIABLE}=1, got {on_value!r}")
    off_without = _remove_control(off_config)
    on_without = _remove_control(on_config)
    if _canonical_json(off_without) != _canonical_json(on_without):
        pointer = _first_difference(off_without, on_without)
        raise ControlVariableError(
            f"OFF/ON run configs differ outside {CONTROL_VARIABLE}; first difference at {pointer}"
        )
    return {
        "name": CONTROL_VARIABLE,
        "off": "unset",
        "on": "1",
        "off_occurrences": len(off_values),
        "on_occurrences": len(on_values),
        "only_difference": True,
    }


def _load_module(path: Path) -> tuple[ModuleType, FileIdentity]:
    identity = hash_regular_file(path)
    module_name = f"incremental_ba_metric_{identity.sha256[:16]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise InvalidEvidenceError(f"cannot create import spec for metric module: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise InvalidEvidenceError(f"metric module import failed ({path}): {exc}") from exc
    return module, identity


def _call_with_context(function: Callable[..., Any], context: Mapping[str, Any]) -> Any:
    signature = inspect.signature(function)
    kwargs: dict[str, Any] = {}
    accepts_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    for name, parameter in signature.parameters.items():
        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if parameter.kind == inspect.Parameter.POSITIONAL_ONLY:
            raise InvalidEvidenceError(
                f"metric function {function.__name__} uses unsupported positional-only parameter {name!r}"
            )
        if name in context:
            kwargs[name] = context[name]
        elif parameter.default is inspect.Parameter.empty:
            raise InvalidEvidenceError(
                f"metric function {function.__name__} requires unknown parameter {name!r}"
            )
    if accepts_kwargs:
        kwargs = dict(context)
    try:
        return function(**kwargs)
    except Exception as exc:
        raise InvalidEvidenceError(f"metric function {function.__name__} failed: {exc}") from exc


def _mapping_result(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidEvidenceError(f"{label} must return a mapping, got {type(value).__name__}")
    if set(value) == {"metrics"} and isinstance(value.get("metrics"), Mapping):
        value = value["metrics"]
    return {str(key): _jsonable(child) for key, child in value.items()}


def _metric_context_for_arm(
    arm: ArmEvidence, evaluation_config: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "arm": arm.name,
        "arm_name": arm.name,
        "arm_dir": arm.directory,
        "run_dir": arm.directory,
        "config": arm.run_config,
        "run_config": arm.run_config,
        "evaluation_config": evaluation_config,
        "ply_path": arm.ply_path,
        "cloud_path": arm.ply_path,
        "npz_path": arm.npz_path,
        "metrics_path": arm.npz_path,
        "ply_info": arm.ply_info,
        "npz_info": arm.npz_info,
        "npz_scalars": arm.npz_scalars,
    }


def compute_plugin_metrics(
    module: ModuleType,
    off: ArmEvidence,
    on: ArmEvidence,
    evaluation_config: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str]:
    ab_function = next(
        (
            getattr(module, name)
            for name in ("compute_ab_metrics", "evaluate_ab_metrics")
            if callable(getattr(module, name, None))
        ),
        None,
    )
    if ab_function is not None:
        context = {
            "off": off,
            "on": on,
            "off_dir": off.directory,
            "on_dir": on.directory,
            "off_config": off.run_config,
            "on_config": on.run_config,
            "off_ply_path": off.ply_path,
            "on_ply_path": on.ply_path,
            "off_npz_path": off.npz_path,
            "on_npz_path": on.npz_path,
            "evaluation_config": evaluation_config,
        }
        result = _call_with_context(ab_function, context)
        if not isinstance(result, Mapping) or not isinstance(result.get("off"), Mapping) or not isinstance(result.get("on"), Mapping):
            raise InvalidEvidenceError(
                f"{ab_function.__name__} must return mappings under 'off' and 'on'"
            )
        return (
            _mapping_result(result["off"], label=f"{ab_function.__name__}['off']"),
            _mapping_result(result["on"], label=f"{ab_function.__name__}['on']"),
            ab_function.__name__,
        )
    arm_function = next(
        (
            getattr(module, name)
            for name in ("compute_metrics", "evaluate_arm", "compute_arm_metrics", "metrics_for_arm")
            if callable(getattr(module, name, None))
        ),
        None,
    )
    if arm_function is None:
        raise InvalidEvidenceError(
            "metric module must export compute_metrics/evaluate_arm/compute_arm_metrics/"
            "metrics_for_arm or compute_ab_metrics/evaluate_ab_metrics"
        )
    off_result = _mapping_result(
        _call_with_context(arm_function, _metric_context_for_arm(off, evaluation_config)),
        label=f"{arm_function.__name__}(off)",
    )
    on_result = _mapping_result(
        _call_with_context(arm_function, _metric_context_for_arm(on, evaluation_config)),
        label=f"{arm_function.__name__}(on)",
    )
    return off_result, on_result, arm_function.__name__


def _deep_merge(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        key = str(key)
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = _jsonable(value)


def assemble_metrics(arm: ArmEvidence, plugin_metrics: Mapping[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    configured_metrics = arm.run_config.get("metrics")
    if isinstance(configured_metrics, Mapping):
        _deep_merge(metrics, configured_metrics)
    metrics["ply"] = dict(arm.ply_info)
    metrics["npz"] = dict(arm.npz_scalars)
    for key, value in arm.npz_scalars.items():
        metrics.setdefault(key, value)
    _deep_merge(metrics, plugin_metrics)
    _check_finite_metrics(metrics)
    return metrics


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(child) for child in value]
    scalar = _python_scalar(value)
    if scalar is not None:
        return scalar
    raise InvalidEvidenceError(f"metric output contains unsupported {type(value).__name__}")


def _check_finite_metrics(value: Any, pointer: str = "") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidEvidenceError(f"metric output is non-finite at {pointer or '/'}")
    if isinstance(value, Mapping):
        for key, child in value.items():
            _check_finite_metrics(child, f"{pointer}/{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _check_finite_metrics(child, f"{pointer}/{index}")


def _threshold_mapping(config: Mapping[str, Any]) -> dict[str, Any]:
    candidates: list[Any] = [config.get("thresholds"), config.get("gates")]
    evaluation = config.get("evaluation")
    if isinstance(evaluation, Mapping):
        candidates.extend((evaluation.get("thresholds"), evaluation.get("gates")))
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            return {str(key): value for key, value in candidate.items()}
        if isinstance(candidate, list):
            converted: dict[str, Any] = {}
            for row in candidate:
                if not isinstance(row, Mapping):
                    continue
                gate_id = row.get("gate") or row.get("gate_id") or row.get("id")
                if not isinstance(gate_id, str):
                    continue
                if gate_id in converted:
                    raise InvalidEvidenceError(f"duplicate threshold gate: {gate_id}")
                converted[gate_id] = row
            if converted:
                return converted
    return {}


def _lookup_metric(metrics: Mapping[str, Any], reference: str) -> Any:
    if reference in metrics:
        return metrics[reference]
    current: Any = metrics
    for part in reference.replace("/", ".").split("."):
        if not part:
            continue
        if not isinstance(current, Mapping) or part not in current:
            raise KeyError(reference)
        current = current[part]
    return current


def _metric_number(value: Any, *, label: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InsufficientEvidenceError(f"{label} is not a numeric metric")
    if not math.isfinite(float(value)):
        raise InvalidEvidenceError(f"{label} is non-finite")
    return value


def _operator_and_threshold(spec: Mapping[str, Any]) -> tuple[str, float | int]:
    operator = spec.get("operator", spec.get("op"))
    threshold = spec.get("threshold", spec.get("value", spec.get("limit")))
    aliases = (
        ("max", "<="),
        ("min", ">="),
        ("max_exclusive", "<"),
        ("min_exclusive", ">"),
        ("equal", "=="),
    )
    if operator is None:
        selected = [(key, op) for key, op in aliases if key in spec]
        if len(selected) == 1:
            key, operator = selected[0]
            threshold = spec[key]
    if operator is None:
        direction = spec.get("direction")
        if direction == "lower_is_better":
            operator = "<="
        elif direction == "higher_is_better":
            operator = ">="
    if operator not in {"<", "<=", ">", ">=", "=="}:
        raise InsufficientEvidenceError("threshold operator is missing or unsupported")
    numeric_threshold = _metric_number(threshold, label="configured threshold")
    return str(operator), numeric_threshold


def _observed_value(
    gate_id: str,
    spec: Mapping[str, Any],
    off_metrics: Mapping[str, Any],
    on_metrics: Mapping[str, Any],
) -> tuple[Any, str, Any]:
    metric_spec = spec.get("metric", gate_id)
    if isinstance(metric_spec, Mapping):
        off_reference = metric_spec.get("off", gate_id)
        on_reference = metric_spec.get("on", gate_id)
    else:
        off_reference = on_reference = metric_spec
    if not isinstance(off_reference, str) or not isinstance(on_reference, str):
        raise InsufficientEvidenceError("threshold metric reference must be a string")
    source = str(spec.get("source", spec.get("arm", "on"))).lower()
    try:
        off_value = _metric_number(
            _lookup_metric(off_metrics, off_reference), label=f"OFF metric {off_reference}"
        )
        on_value = _metric_number(
            _lookup_metric(on_metrics, on_reference), label=f"ON metric {on_reference}"
        )
    except KeyError as exc:
        raise InsufficientEvidenceError(f"missing metric {exc.args[0]!r}") from exc
    if source == "off":
        return off_value, source, {"off": off_value}
    if source == "on":
        return on_value, source, {"on": on_value}
    if source in {"delta", "on_minus_off"}:
        return on_value - off_value, "on_minus_off", {"off": off_value, "on": on_value}
    if source in {"absolute_delta", "abs_delta"}:
        return abs(on_value - off_value), "absolute_delta", {"off": off_value, "on": on_value}
    if source in {"ratio", "on_over_off"}:
        if off_value == 0:
            raise InsufficientEvidenceError("cannot compute on_over_off with zero OFF metric")
        return on_value / off_value, "on_over_off", {"off": off_value, "on": on_value}
    if source == "off_over_on":
        if on_value == 0:
            raise InsufficientEvidenceError("cannot compute off_over_on with zero ON metric")
        return off_value / on_value, source, {"off": off_value, "on": on_value}
    if source in {"relative_change", "relative_delta"}:
        if off_value == 0:
            raise InsufficientEvidenceError("cannot compute relative_change with zero OFF metric")
        return (on_value - off_value) / off_value, "relative_change", {
            "off": off_value,
            "on": on_value,
        }
    if source in {"percent_change", "percent_delta"}:
        if off_value == 0:
            raise InsufficientEvidenceError("cannot compute percent_change with zero OFF metric")
        return 100.0 * (on_value - off_value) / off_value, "percent_change", {
            "off": off_value,
            "on": on_value,
        }
    if source == "min":
        return min(off_value, on_value), source, {"off": off_value, "on": on_value}
    if source == "max":
        return max(off_value, on_value), source, {"off": off_value, "on": on_value}
    raise InsufficientEvidenceError(f"unsupported threshold source: {source!r}")


def _compare(observed: float | int, operator: str, threshold: float | int) -> bool:
    return {
        "<": observed < threshold,
        "<=": observed <= threshold,
        ">": observed > threshold,
        ">=": observed >= threshold,
        "==": observed == threshold,
    }[operator]


def evaluate_gates(
    evaluation_config: Mapping[str, Any],
    off_metrics: Mapping[str, Any],
    on_metrics: Mapping[str, Any],
) -> list[dict[str, Any]]:
    thresholds = _threshold_mapping(evaluation_config)
    results: list[dict[str, Any]] = []
    for gate_id in GATE_IDS:
        spec = thresholds.get(gate_id)
        if not isinstance(spec, Mapping):
            results.append(
                {
                    "gate": gate_id,
                    "status": "insufficient_evidence",
                    "reason": "registered threshold is missing from config",
                }
            )
            continue
        try:
            operator, threshold = _operator_and_threshold(spec)
            observed, source, arm_values = _observed_value(
                gate_id, spec, off_metrics, on_metrics
            )
            passed = _compare(observed, operator, threshold)
            results.append(
                {
                    "gate": gate_id,
                    "metric": spec.get("metric", gate_id),
                    "source": source,
                    "arm_values": arm_values,
                    "observed": observed,
                    "operator": operator,
                    "threshold": threshold,
                    "unit": spec.get("unit"),
                    "status": "pass" if passed else "fail",
                }
            )
        except InsufficientEvidenceError as exc:
            results.append(
                {
                    "gate": gate_id,
                    "status": "insufficient_evidence",
                    "reason": str(exc),
                }
            )
    return results


def _arm_report(arm: ArmEvidence) -> dict[str, Any]:
    root = arm.directory
    required = {
        "run_config": hash_regular_file(arm.run_config_path).as_json(relative_to=root),
        "hash_manifest": hash_regular_file(arm.hash_manifest_path).as_json(relative_to=root),
        "ply": hash_regular_file(arm.ply_path).as_json(relative_to=root),
        "npz": hash_regular_file(arm.npz_path).as_json(relative_to=root),
    }
    required["ply"]["inspection"] = arm.ply_info
    required["npz"]["inspection"] = arm.npz_info
    return {
        "directory": str(root),
        "artifacts": required,
        "hash_manifest_verified_entries": len(arm.identities) - 1,
    }


def _expected_metric_module_hash(config: Mapping[str, Any]) -> str | None:
    direct = config.get("metric_module_sha256")
    if isinstance(direct, str):
        return direct.lower()
    module = config.get("metric_module")
    if isinstance(module, Mapping) and isinstance(module.get("sha256"), str):
        return str(module["sha256"]).lower()
    return None


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    evaluation_config_path = Path(args.config).resolve(strict=True)
    metric_module_path = Path(args.metric_module).resolve(strict=True)
    evaluation_config = load_json(evaluation_config_path)
    config_identity = hash_regular_file(evaluation_config_path)
    module, module_identity = _load_module(metric_module_path)
    expected_module_hash = _expected_metric_module_hash(evaluation_config)
    if expected_module_hash is not None:
        if not SHA256_RE.fullmatch(expected_module_hash):
            raise InvalidEvidenceError("metric_module_sha256 is not a SHA-256 digest")
        if module_identity.sha256 != expected_module_hash:
            raise InvalidEvidenceError(
                "metric module SHA-256 mismatch: "
                f"expected {expected_module_hash}, got {module_identity.sha256}"
            )

    off_cli = {
        "run_config": args.off_run_config,
        "hash_manifest": args.off_hash_manifest,
        "ply": args.off_ply,
        "npz": args.off_npz,
    }
    on_cli = {
        "run_config": args.on_run_config,
        "hash_manifest": args.on_hash_manifest,
        "ply": args.on_ply,
        "npz": args.on_npz,
    }
    off = load_arm_evidence("off", Path(args.off_dir), evaluation_config, off_cli)
    on = load_arm_evidence("on", Path(args.on_dir), evaluation_config, on_cli)
    control = validate_control_variable(off.run_config, on.run_config, evaluation_config)
    off_plugin, on_plugin, plugin_entrypoint = compute_plugin_metrics(
        module, off, on, evaluation_config
    )
    off_metrics = assemble_metrics(off, off_plugin)
    on_metrics = assemble_metrics(on, on_plugin)
    gates = evaluate_gates(evaluation_config, off_metrics, on_metrics)
    summary = {
        "total": len(gates),
        "pass": sum(row["status"] == "pass" for row in gates),
        "fail": sum(row["status"] == "fail" for row in gates),
        "insufficient_evidence": sum(
            row["status"] == "insufficient_evidence" for row in gates
        ),
    }
    if summary["insufficient_evidence"]:
        verdict = "insufficient_evidence"
    elif summary["fail"]:
        verdict = "fail"
    else:
        verdict = "pass"
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "control_variable": control,
        "inputs": {
            "evaluation_config": config_identity.as_json(),
            "metric_module": {
                **module_identity.as_json(),
                "entrypoint": plugin_entrypoint,
                "hash_pinned_by_config": expected_module_hash is not None,
            },
            "arms": {"off": _arm_report(off), "on": _arm_report(on)},
        },
        "metrics": {"off": off_metrics, "on": on_metrics},
        "gates": gates,
        "summary": summary,
    }


def _minimal_error_report(verdict: str, error: Exception) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "error": {"type": type(error).__name__, "message": str(error)},
        "control_variable": {
            "name": CONTROL_VARIABLE,
            "off": "unset",
            "on": "1",
            "only_difference": False,
        },
        "gates": [],
        "summary": {
            "total": len(GATE_IDS),
            "pass": 0,
            "fail": 0,
            "insufficient_evidence": len(GATE_IDS)
            if verdict == "insufficient_evidence"
            else 0,
        },
    }


def _render_report(report: Mapping[str, Any], indent: int) -> str:
    return json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        indent=indent,
        allow_nan=False,
    ) + "\n"


def _write_report(output: str, rendered: str) -> None:
    if output == "-":
        return
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(rendered)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate incremental global BA OFF/ON evidence using nine "
            "config-supplied gates."
        )
    )
    parser.add_argument("--off-dir", required=True, help="OFF arm evidence directory")
    parser.add_argument("--on-dir", required=True, help="ON arm evidence directory")
    parser.add_argument("--config", required=True, help="evaluation config JSON")
    parser.add_argument("--metric-module", required=True, help="Python metric module")
    parser.add_argument("--output", required=True, help="verdict JSON path, or '-' for stdout only")
    parser.add_argument("--off-run-config", help="OFF run config path relative to OFF dir")
    parser.add_argument("--on-run-config", help="ON run config path relative to ON dir")
    parser.add_argument("--off-hash-manifest", help="OFF SHA-256 manifest relative to OFF dir")
    parser.add_argument("--on-hash-manifest", help="ON SHA-256 manifest relative to ON dir")
    parser.add_argument("--off-ply", help="OFF PLY path relative to OFF dir")
    parser.add_argument("--on-ply", help="ON PLY path relative to ON dir")
    parser.add_argument("--off-npz", help="OFF NPZ path relative to OFF dir")
    parser.add_argument("--on-npz", help="ON NPZ path relative to ON dir")
    parser.add_argument("--indent", type=int, default=2, choices=range(0, 9))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = evaluate(args)
        exit_code = {"pass": 0, "fail": 1, "insufficient_evidence": 3}[report["verdict"]]
    except (ControlVariableError, InvalidEvidenceError) as exc:
        report = _minimal_error_report("invalid", exc)
        exit_code = 2
    except (InsufficientEvidenceError, FileNotFoundError) as exc:
        report = _minimal_error_report("insufficient_evidence", exc)
        exit_code = 3
    except Exception as exc:  # fail closed without losing a machine-readable verdict
        report = _minimal_error_report("invalid", exc)
        exit_code = 2
    rendered = _render_report(report, args.indent)
    _write_report(args.output, rendered)
    sys.stdout.write(rendered)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
