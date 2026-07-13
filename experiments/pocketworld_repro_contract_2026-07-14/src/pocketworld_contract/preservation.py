"""Fail-closed helpers for planning local research-evidence preservation."""

from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import re
import stat
import sys
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

GIB = 1024**3
MIB = 1024**2
_FIXED_DISK_HEADROOM_BYTES = (15 * GIB) + (256 * MIB)
_DF_LINE_COUNT = 2
_MINIMUM_MEMORY_PERCENT = 20.0
_MAXIMUM_MEMORY_PERCENT = 100.0
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_MEMORY_PERCENT_RE = re.compile(
    r"^System-wide memory free percentage:\s*([0-9]+(?:\.[0-9]+)?)%\s*$",
    re.MULTILINE,
)
_PAYLOAD_SUFFIXES = frozenset(
    {
        ".db",
        ".db-shm",
        ".db-wal",
        ".jpeg",
        ".jpg",
        ".npy",
        ".npz",
        ".ply",
        ".png",
        ".sqlite",
        ".sqlite3",
    }
)
_CAPTURE_ROOT_PARTS = ("data", "pocketworld_captures")
CLONE_NOOWNERCOPY = 0x2
CLONE_NOFOLLOW_ANY = 0x8
CLONE_FLAGS = CLONE_NOOWNERCOPY | CLONE_NOFOLLOW_ANY


class BatchMapError(ValueError):
    """Raised when a preservation batch map is ambiguous or inconsistent."""


class ResourceSnapshotError(ValueError):
    """Raised when resource observations cannot be parsed or trusted."""


@dataclass(frozen=True)
class ResourceSnapshot:
    """Observed free resources; callers collect the command output externally."""

    free_disk_bytes: int
    memory_available_percent: float


@dataclass(frozen=True)
class ResourceGate:
    """Decision details for the conservative per-batch resource gate."""

    allowed: bool
    disk_ok: bool
    memory_ok: bool
    required_disk_bytes: int


class GitPathViolation(NamedTuple):
    """A payload or non-metadata path that must not enter Git."""

    path: str
    reason: str


class CloneFileError(RuntimeError):
    """Raised when a no-fallback clone cannot be proven byte-identical."""


class CloneVerification(NamedTuple):
    """Verified identity of a successfully cloned regular file."""

    bytes: int
    sha256: str


class _PreparedClone(NamedTuple):
    source: Path
    destination: Path
    source_bytes: int
    source_sha256: str
    source_identity: tuple[int, int, int, int, int]


def required_disk_bytes(batch_bytes: int) -> int:
    """Return the conservative free-disk requirement for one preservation batch."""
    if type(batch_bytes) is not int or batch_bytes < 0:
        raise BatchMapError("batch_bytes must be a non-negative integer")
    return _FIXED_DISK_HEADROOM_BYTES + (2 * batch_bytes)


def parse_resource_snapshot(df_output: str, memory_pressure_output: str) -> ResourceSnapshot:
    """Parse one ``df -k`` row and one macOS ``memory_pressure -Q`` percentage."""
    if not isinstance(df_output, str) or not isinstance(memory_pressure_output, str):
        raise ResourceSnapshotError("resource command outputs must be strings")
    lines = [line for line in df_output.splitlines() if line.strip()]
    if len(lines) != _DF_LINE_COUNT:
        raise ResourceSnapshotError("df output must contain exactly one header and one data row")
    header = lines[0].split()
    row = lines[1].split()
    try:
        available_index = header.index("Available")
        available_kib = int(row[available_index])
    except (IndexError, ValueError) as error:
        raise ResourceSnapshotError("df output has no unambiguous Available value") from error
    if available_kib < 0:
        raise ResourceSnapshotError("df Available value must be non-negative")

    matches = _MEMORY_PERCENT_RE.findall(memory_pressure_output)
    if len(matches) != 1:
        raise ResourceSnapshotError(
            "memory_pressure output must contain exactly one free-percentage value"
        )
    memory_percent = float(matches[0])
    snapshot = ResourceSnapshot(
        free_disk_bytes=available_kib * 1024,
        memory_available_percent=memory_percent,
    )
    _validate_resource_snapshot(snapshot)
    return snapshot


def _validate_resource_snapshot(snapshot: ResourceSnapshot) -> None:
    if type(snapshot.free_disk_bytes) is not int or snapshot.free_disk_bytes < 0:
        raise ResourceSnapshotError("free_disk_bytes must be a non-negative integer")
    memory_percent = snapshot.memory_available_percent
    if (
        type(memory_percent) not in {int, float}
        or not 0 <= memory_percent <= _MAXIMUM_MEMORY_PERCENT
    ):
        raise ResourceSnapshotError("memory_available_percent must be between 0 and 100")


def evaluate_resource_gate(snapshot: ResourceSnapshot, batch_bytes: int) -> ResourceGate:
    """Evaluate free disk and memory without launching any command or mutating state."""
    if not isinstance(snapshot, ResourceSnapshot):
        raise ResourceSnapshotError("snapshot must be a ResourceSnapshot")
    _validate_resource_snapshot(snapshot)
    try:
        required = required_disk_bytes(batch_bytes)
    except BatchMapError as error:
        raise ResourceSnapshotError(str(error)) from error
    disk_ok = snapshot.free_disk_bytes >= required
    memory_ok = snapshot.memory_available_percent >= _MINIMUM_MEMORY_PERCENT
    return ResourceGate(
        allowed=disk_ok and memory_ok,
        disk_ok=disk_ok,
        memory_ok=memory_ok,
        required_disk_bytes=required,
    )


def _normalized_git_path(value: object) -> PurePosixPath | None:
    if (
        not isinstance(value, str)
        or not value
        or any(character in value for character in "\x00\r\n")
    ):
        return None
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return None
    return path


def find_forbidden_git_paths(paths: object) -> tuple[GitPathViolation, ...]:
    """Classify staged/history names without invoking Git or touching the index."""
    candidates = [paths] if isinstance(paths, (str, bytes)) else paths
    if not isinstance(candidates, Iterable):
        candidates = [candidates]

    violations: list[GitPathViolation] = []
    for raw_path in candidates:
        display_path = raw_path if isinstance(raw_path, str) else repr(raw_path)
        path = _normalized_git_path(raw_path)
        if path is None:
            violations.append(GitPathViolation(path=display_path, reason="invalid_path"))
            continue
        if path.suffix.lower() in _PAYLOAD_SUFFIXES:
            violations.append(GitPathViolation(path=display_path, reason="payload_suffix"))
            continue
        in_capture_root = path.parts[: len(_CAPTURE_ROOT_PARTS)] == _CAPTURE_ROOT_PARTS
        allowed_capture_metadata = path.name == ".gitignore" or path.suffix == ".dvc"
        if in_capture_root and not allowed_capture_metadata:
            violations.append(
                GitPathViolation(path=display_path, reason="capture_root_metadata_only")
            )
    return tuple(violations)


def _absolute_lexical_path(path: Path, context: str) -> Path:
    if any(part == ".." for part in path.parts):
        raise CloneFileError(f"{context} must not contain parent traversal")
    return path if path.is_absolute() else Path.cwd() / path


def _assert_no_symlink_chain(path: Path, *, leaf_may_be_missing: bool, context: str) -> None:
    absolute = _absolute_lexical_path(path, context)
    current = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for index, part in enumerate(parts):
        current /= part
        is_leaf = index == len(parts) - 1
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if leaf_may_be_missing and is_leaf:
                return
            raise CloneFileError(f"{context} path component does not exist: {current}") from None
        if stat.S_ISLNK(metadata.st_mode):
            raise CloneFileError(f"{context} path chain must not contain symlinks: {current}")
        if not is_leaf and not stat.S_ISDIR(metadata.st_mode):
            raise CloneFileError(f"{context} parent component is not a directory: {current}")


def _stable_stat_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _sha256_regular(path: Path) -> tuple[int, str, tuple[int, int, int, int, int]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise CloneFileError(
            f"cannot open regular file without following symlinks: {path}"
        ) from error
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise CloneFileError(f"path is not a regular file: {path}")
        digest = hashlib.sha256()
        while chunk := os.read(descriptor, 1024 * 1024):
            digest.update(chunk)
        after = os.fstat(descriptor)
        if _stable_stat_identity(before) != _stable_stat_identity(after):
            raise CloneFileError(f"file changed while hashing: {path}")
        return after.st_size, digest.hexdigest(), _stable_stat_identity(after)
    finally:
        os.close(descriptor)


def _system_clonefile(source: bytes, destination: bytes, flags: int) -> int:
    if sys.platform != "darwin":
        raise CloneFileError("macOS clonefile is unavailable on this platform")
    library = ctypes.CDLL(None, use_errno=True)
    try:
        clone = library.clonefile
    except AttributeError as error:
        raise CloneFileError("macOS libc does not expose clonefile") from error
    clone.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    clone.restype = ctypes.c_int
    return int(clone(source, destination, flags))


def _cleanup_new_destination(destination: Path) -> None:
    try:
        metadata = os.lstat(destination)
    except FileNotFoundError:
        return
    if stat.S_ISDIR(metadata.st_mode):
        return
    with suppress(FileNotFoundError):
        destination.unlink()


def _prepare_clone(source: Path, destination: Path) -> _PreparedClone:
    source = _absolute_lexical_path(Path(source), "source")
    destination = _absolute_lexical_path(Path(destination), "destination")
    _assert_no_symlink_chain(source, leaf_may_be_missing=False, context="source")
    _assert_no_symlink_chain(destination, leaf_may_be_missing=True, context="destination")
    try:
        source_metadata = os.lstat(source)
    except FileNotFoundError as error:
        raise CloneFileError("source does not exist") from error
    if not stat.S_ISREG(source_metadata.st_mode):
        raise CloneFileError("source must be a regular file")
    try:
        os.lstat(destination)
    except FileNotFoundError:
        pass
    else:
        raise CloneFileError("destination must not exist")

    source_size, source_digest, source_identity = _sha256_regular(source)
    if _stable_stat_identity(os.lstat(source)) != source_identity:
        raise CloneFileError("source changed before clonefile")
    return _PreparedClone(
        source=source,
        destination=destination,
        source_bytes=source_size,
        source_sha256=source_digest,
        source_identity=source_identity,
    )


def _invoke_clonefile(
    prepared: _PreparedClone,
    clonefile_fn: Callable[[bytes, bytes, int], int],
) -> None:
    result = clonefile_fn(
        os.fsencode(prepared.source),
        os.fsencode(prepared.destination),
        CLONE_FLAGS,
    )
    if result != 0:
        error_number = ctypes.get_errno() or errno.EIO
        raise CloneFileError(f"clonefile failed with errno {error_number}")


def _verify_cloned_file(prepared: _PreparedClone) -> CloneVerification:
    try:
        destination_metadata = os.lstat(prepared.destination)
    except FileNotFoundError as error:
        raise CloneFileError("clonefile reported success without creating destination") from error
    if not stat.S_ISREG(destination_metadata.st_mode):
        raise CloneFileError("clonefile destination is not a regular file")
    if _stable_stat_identity(os.lstat(prepared.source)) != prepared.source_identity:
        raise CloneFileError("source changed during clonefile")

    destination_size, destination_digest, destination_identity = _sha256_regular(
        prepared.destination
    )
    source_size_after, source_digest_after, source_identity_after = _sha256_regular(prepared.source)
    if source_identity_after != prepared.source_identity:
        raise CloneFileError("source changed during verification")
    if _stable_stat_identity(os.lstat(prepared.destination)) != destination_identity:
        raise CloneFileError("destination changed during verification")
    if (
        prepared.source_bytes != source_size_after
        or prepared.source_bytes != destination_size
        or prepared.source_sha256 != source_digest_after
        or prepared.source_sha256 != destination_digest
    ):
        raise CloneFileError("clonefile size or SHA-256 mismatch")
    return CloneVerification(bytes=prepared.source_bytes, sha256=prepared.source_sha256)


def clonefile_regular(
    source: Path,
    destination: Path,
    *,
    clonefile_fn: Callable[[bytes, bytes, int], int] | None = None,
) -> CloneVerification:
    """Clone one regular file with no fallback, then verify exact size and SHA-256."""
    prepared = _prepare_clone(source, destination)
    clone = clonefile_fn or _system_clonefile
    try:
        _invoke_clonefile(prepared, clone)
        return _verify_cloned_file(prepared)
    except BaseException:
        _cleanup_new_destination(prepared.destination)
        raise


def _mapping(value: object, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BatchMapError(f"{context} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], context: str) -> None:
    actual = set(value)
    if actual != expected:
        extra = sorted(actual - expected)
        missing = sorted(expected - actual)
        raise BatchMapError(f"unexpected {context} keys: extra={extra!r}, missing={missing!r}")


def _nonempty_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise BatchMapError(f"{context} must be a non-empty normalized string")
    return value


def _sha256(value: object, context: str) -> str:
    result = _nonempty_string(value, context)
    if _SHA256_RE.fullmatch(result) is None:
        raise BatchMapError(f"{context} must be a lowercase full SHA-256")
    return result


def _nonnegative_integer(value: object, context: str) -> int:
    if type(value) is not int or value < 0:
        raise BatchMapError(f"{context} must be a non-negative integer")
    return value


def _repo_relative_path(value: object, context: str) -> str:
    result = _nonempty_string(value, context)
    path = PurePosixPath(result)
    if (
        path.is_absolute()
        or path.as_posix() != result
        or "\\" in result
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise BatchMapError(f"{context} must be a normalized repo-relative POSIX path")
    return result


def _validate_source_entry(value: object, context: str) -> tuple[str, int]:
    entry = _mapping(value, context)
    _exact_keys(entry, {"bytes", "sha256", "source_relative_path"}, context)
    source_path = _repo_relative_path(
        entry["source_relative_path"], f"{context}.source_relative_path"
    )
    source_bytes = _nonnegative_integer(entry["bytes"], f"{context}.bytes")
    _sha256(entry["sha256"], f"{context}.sha256")
    return source_path, source_bytes


def _validate_source_manifest(value: object, context: str) -> tuple[str, int]:
    manifest = _mapping(value, context)
    _exact_keys(
        manifest,
        {"asset_count", "collection_id", "path", "sha256", "total_bytes"},
        context,
    )
    _nonempty_string(manifest["collection_id"], f"{context}.collection_id")
    manifest_path = _repo_relative_path(manifest["path"], f"{context}.path")
    asset_count = _nonnegative_integer(manifest["asset_count"], f"{context}.asset_count")
    if asset_count == 0:
        raise BatchMapError(f"{context}.asset_count must be positive")
    _sha256(manifest["sha256"], f"{context}.sha256")
    total_bytes = _nonnegative_integer(manifest["total_bytes"], f"{context}.total_bytes")
    return manifest_path, total_bytes


def _record_unique(value: str, seen: set[str], context: str) -> None:
    if value in seen:
        raise BatchMapError(f"duplicate {context}: {value}")
    seen.add(value)


def _validate_source_documents(source_documents: object) -> None:
    if not isinstance(source_documents, list) or not source_documents:
        raise BatchMapError("source_documents must be a non-empty array")
    document_ids: set[str] = set()
    document_paths: set[str] = set()
    for index, raw_source in enumerate(source_documents):
        context = f"source_documents[{index}]"
        source = _mapping(raw_source, context)
        _exact_keys(source, {"document_id", "path", "sha256"}, context)
        document_id = _nonempty_string(source["document_id"], f"{context}.document_id")
        path = _repo_relative_path(source["path"], f"{context}.path")
        _sha256(source["sha256"], f"{context}.sha256")
        _record_unique(document_id, document_ids, "source document_id")
        _record_unique(path, document_paths, "source document path")


def _validate_evidence_ids(
    value: object,
    context: str,
    global_evidence_ids: set[str],
) -> None:
    if not isinstance(value, list) or not value:
        raise BatchMapError(f"{context}.evidence_ids must be a non-empty array")
    local_evidence_ids: set[str] = set()
    for index, raw_evidence_id in enumerate(value):
        evidence_id = _nonempty_string(raw_evidence_id, f"{context}.evidence_ids[{index}]")
        _record_unique(evidence_id, local_evidence_ids, "evidence_id")
        _record_unique(evidence_id, global_evidence_ids, "evidence_id")


def _validate_batch_source(
    batch: dict[str, Any],
    context: str,
    batch_bytes: int,
    source_references: set[str],
) -> None:
    source_entries = batch["source_entries"]
    source_manifest = batch["source_manifest"]
    uses_entries = isinstance(source_entries, list) and bool(source_entries)
    uses_manifest = isinstance(source_manifest, dict)
    if uses_entries == uses_manifest:
        raise BatchMapError(f"{context} must use exactly one source form")
    if uses_entries:
        if source_manifest is not None:
            raise BatchMapError(f"{context} must use exactly one source form")
        source_bytes = 0
        for index, raw_entry in enumerate(source_entries):
            source_path, entry_bytes = _validate_source_entry(
                raw_entry,
                f"{context}.source_entries[{index}]",
            )
            _record_unique(source_path, source_references, "source reference")
            source_bytes += entry_bytes
        if source_bytes != batch_bytes:
            raise BatchMapError(f"{context}.batch_bytes does not equal source entry byte sum")
        return
    if source_entries is not None:
        raise BatchMapError(f"{context} must use exactly one source form")
    manifest_path, manifest_bytes = _validate_source_manifest(
        source_manifest,
        f"{context}.source_manifest",
    )
    _record_unique(manifest_path, source_references, "source reference")
    if manifest_bytes != batch_bytes:
        raise BatchMapError(f"{context}.batch_bytes does not equal source manifest total_bytes")


def _validate_batches(
    batches: object,
) -> tuple[int, set[str], set[str], set[str]]:
    if not isinstance(batches, list) or not batches:
        raise BatchMapError("batches must be a non-empty array")
    batch_ids: set[str] = set()
    targets: set[str] = set()
    evidence_ids: set[str] = set()
    source_references: set[str] = set()
    payload_bytes = 0
    for index, raw_batch in enumerate(batches):
        context = f"batches[{index}]"
        batch = _mapping(raw_batch, context)
        _exact_keys(
            batch,
            {
                "batch_bytes",
                "batch_id",
                "dvc_target",
                "evidence_ids",
                "source_entries",
                "source_manifest",
            },
            context,
        )
        batch_id = _nonempty_string(batch["batch_id"], f"{context}.batch_id")
        target = _repo_relative_path(batch["dvc_target"], f"{context}.dvc_target")
        batch_bytes = _nonnegative_integer(batch["batch_bytes"], f"{context}.batch_bytes")
        _record_unique(batch_id, batch_ids, "batch_id")
        _record_unique(target, targets, "dvc_target")
        _validate_evidence_ids(batch["evidence_ids"], context, evidence_ids)
        _validate_batch_source(batch, context, batch_bytes, source_references)
        payload_bytes += batch_bytes
    return payload_bytes, evidence_ids, source_references, targets


def _validate_nonoverlapping_targets(targets: set[str]) -> None:
    sorted_targets = sorted(PurePosixPath(target).parts for target in targets)
    for previous, current in pairwise(sorted_targets):
        common_length = min(len(previous), len(current))
        if previous[:common_length] == current[:common_length]:
            raise BatchMapError("dvc_target values must not overlap")


def _validate_exclusions(
    exclusions: object,
    evidence_ids: set[str],
    source_references: set[str],
) -> None:
    if not isinstance(exclusions, list) or not exclusions:
        raise BatchMapError("exclusions must be a non-empty array")
    exclusion_ids: set[str] = set()
    for index, raw_exclusion in enumerate(exclusions):
        context = f"exclusions[{index}]"
        exclusion = _mapping(raw_exclusion, context)
        _exact_keys(
            exclusion,
            {"evidence_id", "persistent_copy_eligible", "reason", "source_relative_path"},
            context,
        )
        evidence_id = _nonempty_string(exclusion["evidence_id"], f"{context}.evidence_id")
        source_path = _repo_relative_path(
            exclusion["source_relative_path"],
            f"{context}.source_relative_path",
        )
        _nonempty_string(exclusion["reason"], f"{context}.reason")
        if exclusion["persistent_copy_eligible"] is not False:
            raise BatchMapError(f"{context}.persistent_copy_eligible must be false")
        if evidence_id in evidence_ids:
            raise BatchMapError(f"duplicate or included exclusion evidence_id: {evidence_id}")
        _record_unique(evidence_id, exclusion_ids, "exclusion evidence_id")
        if source_path in source_references:
            raise BatchMapError(f"excluded source was included in a batch: {source_path}")


def _validate_totals(totals_value: object, batch_count: int, payload_bytes: int) -> None:
    totals = _mapping(totals_value, "totals")
    _exact_keys(totals, {"batch_count", "payload_bytes"}, "totals")
    if _nonnegative_integer(totals["batch_count"], "totals.batch_count") != batch_count:
        raise BatchMapError("totals.batch_count does not equal batch count")
    if _nonnegative_integer(totals["payload_bytes"], "totals.payload_bytes") != payload_bytes:
        raise BatchMapError("totals.payload_bytes does not equal batch byte sum")


def validate_batch_map(document: object) -> None:
    """Validate the closed preservation batch-map contract without performing I/O."""
    root = _mapping(document, "root")
    _exact_keys(
        root,
        {
            "batch_map_id",
            "batches",
            "exclusions",
            "hash_algorithm",
            "schema_version",
            "source_documents",
            "totals",
        },
        "root",
    )
    _nonempty_string(root["batch_map_id"], "batch_map_id")
    if root["schema_version"] != 1:
        raise BatchMapError("schema_version must equal 1")
    if root["hash_algorithm"] != "sha256":
        raise BatchMapError("hash_algorithm must equal sha256")
    _validate_source_documents(root["source_documents"])
    payload_bytes, evidence_ids, source_references, targets = _validate_batches(root["batches"])
    _validate_nonoverlapping_targets(targets)
    _validate_exclusions(root["exclusions"], evidence_ids, source_references)
    batches = root["batches"]
    if not isinstance(batches, list):
        raise BatchMapError("batches must be an array")
    _validate_totals(root["totals"], len(batches), payload_bytes)
