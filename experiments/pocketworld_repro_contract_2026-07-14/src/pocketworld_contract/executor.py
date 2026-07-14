"""Serial, resumable execution for validated preservation batches."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .manifest import ContractError, safe_relative_path
from .preservation import CloneVerification, ResourceGate, clonefile_regular

_HASH_CHUNK_BYTES = 1024 * 1024
_MAXIMUM_MANIFEST_BYTES = 16 * 1024 * 1024
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_MANIFEST_KEYS = frozenset({"assets", "collection_id", "schema_version"})
_MANIFEST_ASSET_KEYS = frozenset(
    {
        "bytes",
        "evidence_role",
        "license_status",
        "lineage_contains_noncommercial",
        "path",
        "platform_qualification",
        "role",
        "sha256",
    }
)

ResourceDecision = ResourceGate | bool | None
ResourceCheck = Callable[[int], ResourceDecision]


class ExecutionError(RuntimeError):
    """Raised when a batch cannot be executed without weakening its contract."""


@dataclass(frozen=True, slots=True)
class ExecutionSummary:
    """Bounded counters for one completed preservation batch."""

    batch_id: str
    total_files: int
    cloned_files: int
    resumed_files: int
    verified_bytes: int
    cleanup_warning_count: int


@dataclass(frozen=True, slots=True)
class _FilePlan:
    source_root: Path
    source_relative_path: str
    source_display_path: str
    destination_relative_path: str
    expected_bytes: int
    expected_sha256: str


@dataclass(frozen=True, slots=True)
class _FileIdentity:
    byte_count: int
    sha256: str


class _RelativePathMissingError(FileNotFoundError):
    pass


def execute_batch(
    batch: Mapping[str, object],
    *,
    repository_root: str | os.PathLike[str],
    source_roots: Mapping[str, str | os.PathLike[str]],
    resource_check: ResourceCheck,
) -> ExecutionSummary:
    """Preserve one validated batch without DVC, networking, or copy fallback.

    Source-entry paths are resolved by their longest matching mapping key. For
    example, ``cap51_livedb/sfm_live.db`` uses the ``cap51_livedb`` root and
    reads ``sfm_live.db`` below it. Manifest batches use their ``collection_id``
    as the mapping key because manifest asset paths are collection-root-relative.
    A one-entry batch writes its exact ``dvc_target``; multi-entry batches write
    source basenames below that target; manifest assets retain their relative
    paths below the target.

    The callback runs once with the validated batch byte total before any
    manifest, source, or destination filesystem access. It may return ``None``
    or ``True`` to continue, or a passing :class:`ResourceGate`. ``False`` and a
    denied gate stop the whole batch. Existing destinations resume only when
    they are regular files with the exact pinned byte count and SHA-256.
    """
    batch_id = _required_string(batch.get("batch_id"), "batch.batch_id")
    batch_bytes = _required_nonnegative_integer(batch.get("batch_bytes"), "batch.batch_bytes")
    _require_resource_permission(resource_check, batch_bytes)
    repository = _absolute_lexical_path(repository_root, "repository_root")
    roots = _normalized_source_roots(source_roots)
    plans = _plan_files(batch, repository, roots)

    cloned_files = 0
    resumed_files = 0
    verified_bytes = 0
    cleanup_warning_count = 0
    for plan in plans:
        destination_identity = _inspect_optional_regular_under(
            repository,
            plan.destination_relative_path,
            context="destination",
        )
        if destination_identity is not None:
            _require_expected_identity(
                destination_identity,
                plan,
                context="existing destination",
            )
            resumed_files += 1
            verified_bytes += plan.expected_bytes
            continue

        source_identity = _inspect_required_regular_under(
            plan.source_root,
            plan.source_relative_path,
            context=f"source {plan.source_display_path!r}",
        )
        _require_expected_identity(source_identity, plan, context="source")
        _ensure_destination_parent(repository, plan.destination_relative_path)

        source = _join_relative(plan.source_root, plan.source_relative_path)
        destination = _join_relative(repository, plan.destination_relative_path)
        verification = clonefile_regular(source, destination)
        _require_clone_verification(verification, plan)
        published_identity = _inspect_required_regular_under(
            repository,
            plan.destination_relative_path,
            context="published destination",
        )
        _require_expected_identity(published_identity, plan, context="published destination")

        cloned_files += 1
        verified_bytes += plan.expected_bytes
        if verification.cleanup_warning is not None:
            cleanup_warning_count += 1

    return ExecutionSummary(
        batch_id=batch_id,
        total_files=len(plans),
        cloned_files=cloned_files,
        resumed_files=resumed_files,
        verified_bytes=verified_bytes,
        cleanup_warning_count=cleanup_warning_count,
    )


def _plan_files(
    batch: Mapping[str, object],
    repository_root: Path,
    source_roots: Mapping[str, Path],
) -> tuple[_FilePlan, ...]:
    target = _safe_relative(batch.get("dvc_target"), "batch.dvc_target")
    raw_entries = batch.get("source_entries")
    if isinstance(raw_entries, list):
        plans = _plan_source_entries(raw_entries, target, source_roots)
    else:
        plans = _plan_manifest_assets(batch, target, repository_root, source_roots)
    if not plans:
        raise ExecutionError("batch must plan at least one file")
    _require_unique_destinations(plans)
    return plans


def _plan_source_entries(
    raw_entries: list[object],
    target: str,
    source_roots: Mapping[str, Path],
) -> tuple[_FilePlan, ...]:
    entries: list[tuple[str, int, str]] = []
    for index, raw_entry in enumerate(raw_entries):
        entry = _required_mapping(raw_entry, f"batch.source_entries[{index}]")
        source_path = _safe_relative(
            entry.get("source_relative_path"),
            f"batch.source_entries[{index}].source_relative_path",
        )
        byte_count = _required_nonnegative_integer(
            entry.get("bytes"),
            f"batch.source_entries[{index}].bytes",
        )
        digest = _required_sha256(
            entry.get("sha256"),
            f"batch.source_entries[{index}].sha256",
        )
        entries.append((source_path, byte_count, digest))

    plans: list[_FilePlan] = []
    multiple_entries = len(entries) > 1
    for source_path, byte_count, digest in sorted(entries):
        source_root, relative_path = _resolve_entry_source(source_path, source_roots)
        destination_path = (
            _append_relative(target, PurePosixPath(source_path).name)
            if multiple_entries
            else target
        )
        plans.append(
            _FilePlan(
                source_root=source_root,
                source_relative_path=relative_path,
                source_display_path=source_path,
                destination_relative_path=destination_path,
                expected_bytes=byte_count,
                expected_sha256=digest,
            )
        )
    return tuple(plans)


def _resolve_entry_source(
    source_path: str,
    source_roots: Mapping[str, Path],
) -> tuple[Path, str]:
    candidates = [alias for alias in source_roots if source_path.startswith(f"{alias}/")]
    if not candidates:
        raise ExecutionError(f"no explicit source root maps {source_path!r}")
    alias = max(candidates, key=lambda item: (len(PurePosixPath(item).parts), item))
    relative_path = source_path[len(alias) + 1 :]
    return source_roots[alias], _safe_relative(relative_path, "mapped source path")


def _plan_manifest_assets(
    batch: Mapping[str, object],
    target: str,
    repository_root: Path,
    source_roots: Mapping[str, Path],
) -> tuple[_FilePlan, ...]:
    reference = _required_mapping(batch.get("source_manifest"), "batch.source_manifest")
    manifest_path = _safe_relative(reference.get("path"), "batch.source_manifest.path")
    manifest_bytes, manifest_identity = _read_required_regular_under(
        repository_root,
        manifest_path,
        context="source manifest",
        maximum_bytes=_MAXIMUM_MANIFEST_BYTES,
    )
    expected_manifest_sha256 = _required_sha256(
        reference.get("sha256"),
        "batch.source_manifest.sha256",
    )
    if manifest_identity.sha256 != expected_manifest_sha256:
        raise ExecutionError("source manifest does not match its pinned SHA-256")
    try:
        raw_manifest: object = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExecutionError("source manifest is not valid UTF-8 JSON") from error
    manifest = _required_mapping(raw_manifest, "source manifest")
    if set(manifest) != _MANIFEST_KEYS:
        raise ExecutionError("source manifest has unexpected root fields")
    if manifest.get("schema_version") != 1:
        raise ExecutionError("source manifest schema_version must be 1")

    collection_id = _required_string(
        reference.get("collection_id"),
        "batch.source_manifest.collection_id",
    )
    if manifest.get("collection_id") != collection_id:
        raise ExecutionError("source manifest collection_id does not match its batch reference")
    try:
        source_root = source_roots[collection_id]
    except KeyError as error:
        raise ExecutionError(
            f"no explicit source root maps manifest collection {collection_id!r}"
        ) from error

    raw_assets = manifest.get("assets")
    if not isinstance(raw_assets, list):
        raise ExecutionError("source manifest assets must be an array")
    expected_asset_count = _required_nonnegative_integer(
        reference.get("asset_count"),
        "batch.source_manifest.asset_count",
    )
    if len(raw_assets) != expected_asset_count:
        raise ExecutionError("source manifest asset count does not match its batch reference")

    plans = _manifest_file_plans(raw_assets, source_root, target)
    expected_total_bytes = _required_nonnegative_integer(
        reference.get("total_bytes"),
        "batch.source_manifest.total_bytes",
    )
    if sum(plan.expected_bytes for plan in plans) != expected_total_bytes:
        raise ExecutionError("source manifest byte total does not match its batch reference")
    return plans


def _manifest_file_plans(
    raw_assets: list[object],
    source_root: Path,
    target: str,
) -> tuple[_FilePlan, ...]:
    plans: list[_FilePlan] = []
    observed_paths: list[str] = []
    for index, raw_asset in enumerate(raw_assets):
        asset = _required_mapping(raw_asset, f"source manifest asset {index}")
        if set(asset) != _MANIFEST_ASSET_KEYS:
            raise ExecutionError(f"source manifest asset {index} has unexpected fields")
        path = _safe_relative(asset.get("path"), f"source manifest asset {index}.path")
        _validate_manifest_metadata(asset, index)
        plans.append(
            _FilePlan(
                source_root=source_root,
                source_relative_path=path,
                source_display_path=path,
                destination_relative_path=_append_relative(target, path),
                expected_bytes=_required_nonnegative_integer(
                    asset.get("bytes"),
                    f"source manifest asset {index}.bytes",
                ),
                expected_sha256=_required_sha256(
                    asset.get("sha256"),
                    f"source manifest asset {index}.sha256",
                ),
            )
        )
        observed_paths.append(path)
    if observed_paths != sorted(observed_paths) or len(set(observed_paths)) != len(observed_paths):
        raise ExecutionError("source manifest assets must have unique canonical sorted paths")
    return tuple(plans)


def _validate_manifest_metadata(asset: Mapping[str, object], index: int) -> None:
    for field in ("evidence_role", "license_status", "platform_qualification", "role"):
        _required_string(asset.get(field), f"source manifest asset {index}.{field}")
    if type(asset.get("lineage_contains_noncommercial")) is not bool:
        raise ExecutionError(
            f"source manifest asset {index}.lineage_contains_noncommercial must be boolean"
        )


def _normalized_source_roots(
    source_roots: Mapping[str, str | os.PathLike[str]],
) -> dict[str, Path]:
    if not isinstance(source_roots, Mapping):
        raise ExecutionError("source_roots must be a mapping")
    normalized: dict[str, Path] = {}
    for raw_alias, raw_root in source_roots.items():
        alias = _safe_relative(raw_alias, "source root key")
        normalized[alias] = _absolute_lexical_path(raw_root, f"source root {alias!r}")
    return normalized


def _absolute_lexical_path(
    raw_path: str | os.PathLike[str],
    context: str,
) -> Path:
    try:
        path = Path(raw_path)
    except TypeError as error:
        raise ExecutionError(f"{context} must be a filesystem path") from error
    if not path.is_absolute() or ".." in path.parts:
        raise ExecutionError(f"{context} must be an absolute path without parent traversal")
    return path


def _safe_relative(value: object, context: str) -> str:
    if not isinstance(value, str):
        raise ExecutionError(f"{context} must be a string")
    try:
        return safe_relative_path(value)
    except ContractError as error:
        raise ExecutionError(f"unsafe {context}: {error}") from error


def _required_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ExecutionError(f"{context} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise ExecutionError(f"{context} keys must be strings")
    return value


def _required_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExecutionError(f"{context} must be a non-empty string")
    return value


def _required_nonnegative_integer(value: object, context: str) -> int:
    if type(value) is not int or value < 0:
        raise ExecutionError(f"{context} must be a non-negative integer")
    return value


def _required_sha256(value: object, context: str) -> str:
    digest = _required_string(value, context)
    if _SHA256_PATTERN.fullmatch(digest) is None:
        raise ExecutionError(f"{context} must be a lowercase full SHA-256")
    return digest


def _append_relative(parent: str, child: str) -> str:
    return _safe_relative(f"{parent}/{child}", "destination path")


def _join_relative(root: Path, relative_path: str) -> Path:
    return root.joinpath(*PurePosixPath(relative_path).parts)


def _require_unique_destinations(plans: tuple[_FilePlan, ...]) -> None:
    destinations = [plan.destination_relative_path for plan in plans]
    if len(set(destinations)) != len(destinations):
        raise ExecutionError("batch plans duplicate destination paths")


def _require_resource_permission(resource_check: ResourceCheck, file_bytes: int) -> None:
    decision = resource_check(file_bytes)
    if decision is None or decision is True:
        return
    if decision is False or (isinstance(decision, ResourceGate) and not decision.allowed):
        raise ExecutionError("resource check denied preservation before file access")
    if isinstance(decision, ResourceGate):
        return
    raise ExecutionError("resource check must return None, bool, or ResourceGate")


def _require_expected_identity(
    identity: _FileIdentity,
    plan: _FilePlan,
    *,
    context: str,
) -> None:
    if identity.byte_count != plan.expected_bytes or identity.sha256 != plan.expected_sha256:
        raise ExecutionError(
            f"{context} does not match pinned bytes and SHA-256: {plan.destination_relative_path}"
        )


def _require_clone_verification(
    verification: CloneVerification,
    plan: _FilePlan,
) -> None:
    if not isinstance(verification, CloneVerification):
        raise ExecutionError("clonefile_regular returned an invalid verification result")
    if verification.bytes != plan.expected_bytes or verification.sha256 != plan.expected_sha256:
        raise ExecutionError("clonefile_regular verification does not match the pinned source")


def _safe_open_flags(*, directory: bool) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ExecutionError("platform cannot reject filesystem symlinks safely")
    flags = os.O_RDONLY | no_follow | getattr(os, "O_CLOEXEC", 0)
    if directory:
        directory_flag = getattr(os, "O_DIRECTORY", None)
        if directory_flag is None:
            raise ExecutionError("platform cannot anchor filesystem directories safely")
        flags |= directory_flag
    else:
        flags |= getattr(os, "O_BINARY", 0)
    return flags


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_dev,
        first.st_ino,
        stat.S_IFMT(first.st_mode),
    ) == (
        second.st_dev,
        second.st_ino,
        stat.S_IFMT(second.st_mode),
    )


def _stable_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _open_root(root: Path, context: str) -> int:
    try:
        before = root.lstat()
    except OSError as error:
        raise ExecutionError(f"{context} root cannot be inspected safely: {root}") from error
    if stat.S_ISLNK(before.st_mode):
        raise ExecutionError(f"{context} root must not be a symlink: {root}")
    if not stat.S_ISDIR(before.st_mode):
        raise ExecutionError(f"{context} root must be a directory: {root}")
    try:
        descriptor = os.open(root, _safe_open_flags(directory=True))
    except OSError as error:
        raise ExecutionError(f"{context} root cannot be opened safely: {root}") from error
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode) or not _same_file(before, opened):
        os.close(descriptor)
        raise ExecutionError(f"{context} root changed before it was opened: {root}")
    return descriptor


def _open_component(
    parent_descriptor: int,
    name: str,
    *,
    directory: bool,
    context: str,
) -> int:
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        raise ExecutionError("platform cannot open contained paths safely")
    try:
        before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError as error:
        raise _RelativePathMissingError(name) from error
    except OSError as error:
        raise ExecutionError(
            f"{context} path component cannot be inspected safely: {name}"
        ) from error
    if stat.S_ISLNK(before.st_mode):
        raise ExecutionError(f"{context} path component must not be a symlink: {name}")
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(before.st_mode):
        expected_name = "directory" if directory else "regular file"
        raise ExecutionError(f"{context} path component must be a {expected_name}: {name}")
    try:
        descriptor = os.open(
            name,
            _safe_open_flags(directory=directory),
            dir_fd=parent_descriptor,
        )
    except OSError as error:
        raise ExecutionError(f"{context} path component cannot be opened safely: {name}") from error
    opened = os.fstat(descriptor)
    if not expected_type(opened.st_mode) or not _same_file(before, opened):
        os.close(descriptor)
        raise ExecutionError(f"{context} path component changed before open: {name}")
    return descriptor


def _open_relative_regular(root_descriptor: int, relative_path: str, context: str) -> int:
    parts = _safe_relative(relative_path, context).split("/")
    directory_descriptor = os.dup(root_descriptor)
    try:
        for part in parts[:-1]:
            next_descriptor = _open_component(
                directory_descriptor,
                part,
                directory=True,
                context=context,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        return _open_component(
            directory_descriptor,
            parts[-1],
            directory=False,
            context=context,
        )
    finally:
        os.close(directory_descriptor)


def _hash_open_regular(
    descriptor: int,
    *,
    maximum_bytes: int | None = None,
    capture: bool = False,
) -> tuple[_FileIdentity, bytes | None, os.stat_result]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        raise ExecutionError("opened path is not a regular file")
    if maximum_bytes is not None and before.st_size > maximum_bytes:
        raise ExecutionError("source manifest exceeds the bounded metadata size limit")
    digest = hashlib.sha256()
    chunks: list[bytes] | None = [] if capture else None
    byte_count = 0
    while chunk := os.read(descriptor, _HASH_CHUNK_BYTES):
        byte_count += len(chunk)
        if maximum_bytes is not None and byte_count > maximum_bytes:
            raise ExecutionError("source manifest exceeds the bounded metadata size limit")
        digest.update(chunk)
        if chunks is not None:
            chunks.append(chunk)
    after = os.fstat(descriptor)
    if _stable_identity(before) != _stable_identity(after) or byte_count != after.st_size:
        raise ExecutionError("regular file changed while it was hashed")
    payload = b"".join(chunks) if chunks is not None else None
    return _FileIdentity(byte_count=byte_count, sha256=digest.hexdigest()), payload, after


def _inspect_regular_under(
    root: Path,
    relative_path: str,
    *,
    context: str,
) -> _FileIdentity:
    root_descriptor = _open_root(root, context)
    try:
        descriptor = _open_relative_regular(root_descriptor, relative_path, context)
        try:
            identity, _payload, after = _hash_open_regular(descriptor)
        finally:
            os.close(descriptor)
        verification_descriptor = _open_relative_regular(root_descriptor, relative_path, context)
        try:
            current = os.fstat(verification_descriptor)
        finally:
            os.close(verification_descriptor)
        if _stable_identity(after) != _stable_identity(current):
            raise ExecutionError(f"{context} changed after it was hashed")
        return identity
    finally:
        os.close(root_descriptor)


def _inspect_required_regular_under(
    root: Path,
    relative_path: str,
    *,
    context: str,
) -> _FileIdentity:
    try:
        return _inspect_regular_under(root, relative_path, context=context)
    except _RelativePathMissingError as error:
        raise ExecutionError(f"{context} does not exist: {relative_path}") from error


def _inspect_optional_regular_under(
    root: Path,
    relative_path: str,
    *,
    context: str,
) -> _FileIdentity | None:
    try:
        return _inspect_regular_under(root, relative_path, context=context)
    except _RelativePathMissingError:
        return None


def _read_required_regular_under(
    root: Path,
    relative_path: str,
    *,
    context: str,
    maximum_bytes: int,
) -> tuple[bytes, _FileIdentity]:
    root_descriptor = _open_root(root, context)
    try:
        try:
            descriptor = _open_relative_regular(root_descriptor, relative_path, context)
        except _RelativePathMissingError as error:
            raise ExecutionError(f"{context} does not exist: {relative_path}") from error
        try:
            identity, payload, after = _hash_open_regular(
                descriptor,
                maximum_bytes=maximum_bytes,
                capture=True,
            )
        finally:
            os.close(descriptor)
        verification_descriptor = _open_relative_regular(root_descriptor, relative_path, context)
        try:
            current = os.fstat(verification_descriptor)
        finally:
            os.close(verification_descriptor)
        if _stable_identity(after) != _stable_identity(current):
            raise ExecutionError(f"{context} changed after it was read")
    finally:
        os.close(root_descriptor)
    if payload is None:
        raise ExecutionError(f"{context} read ended without payload bytes")
    return payload, identity


def _ensure_destination_parent(repository_root: Path, destination_path: str) -> None:
    parent_parts = _safe_relative(destination_path, "destination path").split("/")[:-1]
    root_descriptor = _open_root(repository_root, "destination")
    directory_descriptor = os.dup(root_descriptor)
    os.close(root_descriptor)
    try:
        for part in parent_parts:
            if os.mkdir not in os.supports_dir_fd:
                raise ExecutionError("platform cannot create contained destination directories")
            try:
                os.mkdir(part, 0o700, dir_fd=directory_descriptor)
            except FileExistsError:
                pass
            except OSError as error:
                raise ExecutionError(
                    f"destination directory cannot be created safely: {part}"
                ) from error
            next_descriptor = _open_component(
                directory_descriptor,
                part,
                directory=True,
                context="destination",
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
    finally:
        os.close(directory_descriptor)
