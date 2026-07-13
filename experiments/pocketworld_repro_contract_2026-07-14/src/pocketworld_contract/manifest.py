from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TypeAlias

HASH_CHUNK_BYTES = 4 * 1024 * 1024
SCHEMA_VERSION = 1
_SCANDIR_SUPPORTS_FD = os.scandir in os.supports_fd

JsonObject: TypeAlias = dict[str, object]

_ROLE_BY_SUFFIX = {
    ".jpg": "capture_image",
    ".jpeg": "capture_image",
    ".png": "derived_image",
    ".json": "metadata",
    ".jsonl": "event_log",
    ".ply": "point_cloud",
    ".npz": "numpy_archive",
    ".db": "sqlite_database",
}
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_MANIFEST_KEYS = frozenset({"schema_version", "collection_id", "assets"})
_ASSET_KEYS = frozenset(
    {
        "path",
        "role",
        "bytes",
        "sha256",
        "license_status",
        "platform_qualification",
        "evidence_role",
        "lineage_contains_noncommercial",
    }
)


class ContractError(ValueError):
    """Raised when an asset collection violates the local research contract."""


@dataclass(frozen=True, slots=True)
class _ExpectedAsset:
    path: str
    byte_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class _CollectionSnapshot:
    files: dict[str, os.stat_result]
    directories: dict[str, _DirectorySnapshot]


@dataclass(frozen=True, slots=True)
class _DirectorySnapshot:
    file_stat: os.stat_result
    names: tuple[str, ...]


def canonical_json(value: object) -> str:
    """Serialize a JSON-compatible value canonically, preserving Unicode."""
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def sha256_file(path: str | os.PathLike[str]) -> str:
    """Hash a file without loading more than four MiB per read."""
    _byte_count, digest = _inspect_regular_file(Path(path))
    return digest


def _hash_descriptor(descriptor: int) -> str:
    digest = hashlib.sha256()
    while chunk := os.read(descriptor, HASH_CHUNK_BYTES):
        digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(path: str) -> str:
    """Return an unambiguous normalized POSIX relative path or raise."""
    if not isinstance(path, str):
        raise ContractError("asset path must be a string")
    if not path:
        raise ContractError("asset path must not be empty")
    if "\\" in path:
        raise ContractError("asset path must use POSIX separators, not backslashes")
    if "\x00" in path:
        raise ContractError("asset path must not contain NUL")
    if PurePosixPath(path).is_absolute() or PureWindowsPath(path).drive:
        raise ContractError(f"asset path must be relative: {path!r}")

    parts = path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ContractError(f"asset path must be normalized without dot traversal: {path!r}")
    return path


def build_collection(  # noqa: PLR0913 - the contract intentionally exposes four separate axes.
    root: str | os.PathLike[str],
    collection_id: str,
    *,
    license_status: str,
    platform_qualification: str,
    evidence_role: str,
    lineage_contains_noncommercial: bool,
    _expected_root: os.stat_result | None = None,
) -> JsonObject:
    """Build a deterministic manifest for every regular file under ``root``."""
    if not isinstance(collection_id, str) or not collection_id:
        raise ContractError("collection_id must be a non-empty string")
    _validate_collection_axes(
        license_status=license_status,
        platform_qualification=platform_qualification,
        evidence_role=evidence_role,
        lineage_contains_noncommercial=lineage_contains_noncommercial,
    )

    root_path, root_descriptor = _open_collection_root(root)
    try:
        if _expected_root is not None and not _same_file(
            _expected_root,
            os.fstat(root_descriptor),
        ):
            raise ContractError(f"collection root changed before scan: {root_path}")
        snapshot = _scan_regular_files(root_descriptor)
        _assert_root_unchanged(root_path, root_descriptor)
        _assert_snapshot_unchanged(root_descriptor, snapshot)
        assets: list[JsonObject] = []
        for relative_path in snapshot.files:
            byte_count, digest = _inspect_relative_regular_file(root_descriptor, relative_path)
            assets.append(
                {
                    "path": relative_path,
                    "role": _role_for_path(relative_path),
                    "bytes": byte_count,
                    "sha256": digest,
                    "license_status": license_status,
                    "platform_qualification": platform_qualification,
                    "evidence_role": evidence_role,
                    "lineage_contains_noncommercial": lineage_contains_noncommercial,
                }
            )
        _assert_snapshot_unchanged(root_descriptor, snapshot)
        _assert_root_unchanged(root_path, root_descriptor)
    finally:
        os.close(root_descriptor)

    return {
        "schema_version": SCHEMA_VERSION,
        "collection_id": collection_id,
        "assets": assets,
    }


def verify_collection(
    root: str | os.PathLike[str],
    manifest: Mapping[str, object],
) -> None:
    """Verify that ``root`` has exactly the safe, unchanged manifest file set."""
    expected = _validate_manifest(manifest)
    root_path, root_descriptor = _open_collection_root(root)
    try:
        snapshot = _scan_regular_files(root_descriptor)
        _assert_root_unchanged(root_path, root_descriptor)
        _assert_snapshot_unchanged(root_descriptor, snapshot)

        expected_paths = set(expected)
        actual_paths = set(snapshot.files)
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        if missing or extra:
            details: list[str] = []
            if missing:
                details.append(f"missing files: {', '.join(missing)}")
            if extra:
                details.append(f"extra files: {', '.join(extra)}")
            raise ContractError("; ".join(details))

        for relative_path in sorted(expected):
            expectation = expected[relative_path]
            byte_count, digest = _inspect_relative_regular_file(
                root_descriptor,
                relative_path,
            )
            if byte_count != expectation.byte_count:
                raise ContractError(f"mutated file size: {relative_path}")
            if digest != expectation.sha256:
                raise ContractError(f"mutated file digest: {relative_path}")
        _assert_snapshot_unchanged(root_descriptor, snapshot)
        _assert_root_unchanged(root_path, root_descriptor)
    finally:
        os.close(root_descriptor)


def require_verdict_eligible(contract: Mapping[str, object]) -> None:
    """Reject any research contract that is not explicitly verdict eligible."""
    if not isinstance(contract, Mapping) or contract.get("status") != "verdict_eligible":
        raise ContractError("contract status must be verdict_eligible")


def _validated_root(root: str | os.PathLike[str]) -> Path:
    root_path = Path(root)
    try:
        root_stat = root_path.lstat()
    except FileNotFoundError as exc:
        raise ContractError(f"collection root does not exist: {root_path}") from exc
    if stat.S_ISLNK(root_stat.st_mode):
        raise ContractError(f"collection root must not be a symlink: {root_path}")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise ContractError(f"collection root must be a directory: {root_path}")
    return root_path


def _scan_regular_files(root_descriptor: int) -> _CollectionSnapshot:
    discovered: dict[str, os.stat_result] = {}
    directories: dict[str, _DirectorySnapshot] = {}
    _scan_directory(root_descriptor, "", discovered, directories)
    return _CollectionSnapshot(
        files=dict(sorted(discovered.items())),
        directories=dict(sorted(directories.items())),
    )


def _scan_directory(
    directory_descriptor: int,
    directory_path: str,
    discovered: dict[str, os.stat_result],
    directories: dict[str, _DirectorySnapshot],
) -> None:
    listing = _enumerate_directory(directory_descriptor, directory_path)
    directories[directory_path] = listing

    for entry_name in listing.names:
        relative_path = safe_relative_path(
            f"{directory_path}/{entry_name}" if directory_path else entry_name
        )
        try:
            entry_stat = os.stat(
                entry_name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise ContractError(f"collection entry changed during scan: {relative_path}") from exc
        if stat.S_ISLNK(entry_stat.st_mode):
            raise ContractError(f"symlink is forbidden in collection: {relative_path}")
        if stat.S_ISDIR(entry_stat.st_mode):
            try:
                child_descriptor = _open_relative_component(
                    directory_descriptor,
                    entry_name,
                    directory=True,
                )
            except ContractError as exc:
                raise ContractError(
                    f"unable to scan collection directory: {relative_path}"
                ) from exc
            try:
                _scan_directory(
                    child_descriptor,
                    relative_path,
                    discovered,
                    directories,
                )
            finally:
                os.close(child_descriptor)
        elif stat.S_ISREG(entry_stat.st_mode):
            discovered[relative_path] = entry_stat
        else:
            raise ContractError(f"collection entry is not a regular file: {relative_path}")

    current = os.fstat(directory_descriptor)
    if not _same_file(listing.file_stat, current) or not _same_metadata(
        listing.file_stat,
        current,
    ):
        display_path = directory_path or "."
        raise ContractError(f"collection directory changed during scan: {display_path}")


def _enumerate_directory(
    directory_descriptor: int,
    directory_path: str,
) -> _DirectorySnapshot:
    if not _SCANDIR_SUPPORTS_FD or os.stat not in os.supports_dir_fd:
        raise ContractError("platform cannot securely enumerate collection directories")
    before = os.fstat(directory_descriptor)
    if not stat.S_ISDIR(before.st_mode):
        display_path = directory_path or "."
        raise ContractError(f"collection directory is not stable: {display_path}")
    try:
        with os.scandir(directory_descriptor) as entries:
            names = tuple(sorted(entry.name for entry in entries))
    except OSError as exc:
        display_path = directory_path or "."
        raise ContractError(f"unable to enumerate collection directory: {display_path}") from exc
    after = os.fstat(directory_descriptor)
    if not _same_file(before, after) or not _same_metadata(before, after):
        display_path = directory_path or "."
        raise ContractError(f"collection directory changed during enumeration: {display_path}")
    return _DirectorySnapshot(file_stat=after, names=names)


def _open_collection_root(root: str | os.PathLike[str]) -> tuple[Path, int]:
    root_path = _validated_root(root)
    before_open = root_path.lstat()
    flags = _safe_open_flags(directory=True)
    try:
        descriptor = os.open(root_path, flags)
    except OSError as exc:
        raise ContractError(f"unable to open collection root safely: {root_path}") from exc
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode) or not _same_file(before_open, opened):
        os.close(descriptor)
        raise ContractError(f"collection root changed before scan: {root_path}")
    return root_path, descriptor


def _assert_root_unchanged(root_path: Path, descriptor: int) -> None:
    try:
        current_path = root_path.lstat()
    except OSError as exc:
        raise ContractError(f"collection root changed during scan: {root_path}") from exc
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(current_path.st_mode)
        or not _same_file(opened, current_path)
        or not _same_metadata(opened, current_path)
    ):
        raise ContractError(f"collection root changed during scan: {root_path}")


def _assert_snapshot_unchanged(
    root_descriptor: int,
    snapshot: _CollectionSnapshot,
) -> None:
    for relative_path, recorded in snapshot.directories.items():
        descriptor = _open_relative_directory(root_descriptor, relative_path)
        try:
            current = _enumerate_directory(descriptor, relative_path)
        finally:
            os.close(descriptor)
        if (
            not _same_file(recorded.file_stat, current.file_stat)
            or not _same_metadata(recorded.file_stat, current.file_stat)
            or recorded.names != current.names
        ):
            display_path = relative_path or "."
            raise ContractError(f"collection directory changed after scan: {display_path}")
    for relative_path, recorded in snapshot.files.items():
        descriptor = _open_relative_regular_file(root_descriptor, relative_path)
        try:
            current = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        if not _same_file(recorded, current) or not _same_metadata(recorded, current):
            raise ContractError(f"collection file changed after scan: {relative_path}")


def _safe_open_flags(*, directory: bool) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    return flags


def _inspect_relative_regular_file(root_descriptor: int, relative_path: str) -> tuple[int, str]:
    descriptor = _open_relative_regular_file(root_descriptor, relative_path)
    try:
        opened = os.fstat(descriptor)
        digest = _hash_descriptor(descriptor)
        after_hash = os.fstat(descriptor)
        if not _same_file(opened, after_hash) or not _same_metadata(opened, after_hash):
            raise ContractError(f"asset changed during hashing: {relative_path}")

        verification_descriptor = _open_relative_regular_file(root_descriptor, relative_path)
        try:
            current_path = os.fstat(verification_descriptor)
        finally:
            os.close(verification_descriptor)
        if not _same_file(after_hash, current_path) or not _same_metadata(
            after_hash,
            current_path,
        ):
            raise ContractError(f"asset changed during hashing: {relative_path}")
        return after_hash.st_size, digest
    finally:
        os.close(descriptor)


def _open_relative_regular_file(root_descriptor: int, relative_path: str) -> int:
    parts = safe_relative_path(relative_path).split("/")
    directory_descriptor = os.dup(root_descriptor)
    try:
        for part in parts[:-1]:
            next_descriptor = _open_relative_component(
                directory_descriptor,
                part,
                directory=True,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        return _open_relative_component(
            directory_descriptor,
            parts[-1],
            directory=False,
        )
    finally:
        os.close(directory_descriptor)


def _open_relative_directory(root_descriptor: int, relative_path: str) -> int:
    if not relative_path:
        return os.dup(root_descriptor)
    parts = safe_relative_path(relative_path).split("/")
    directory_descriptor = os.dup(root_descriptor)
    try:
        for part in parts:
            next_descriptor = _open_relative_component(
                directory_descriptor,
                part,
                directory=True,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        return os.dup(directory_descriptor)
    finally:
        os.close(directory_descriptor)


def _open_relative_component(parent_descriptor: int, name: str, *, directory: bool) -> int:
    if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
        raise ContractError("platform cannot securely open collection-relative paths")
    try:
        before_open = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise ContractError(f"unable to inspect collection path component safely: {name}") from exc
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(before_open.st_mode):
        raise ContractError(f"symlink or changed collection path component is forbidden: {name}")

    try:
        descriptor = os.open(
            name,
            _safe_open_flags(directory=directory),
            dir_fd=parent_descriptor,
        )
    except OSError as exc:
        raise ContractError(f"unable to open collection path component safely: {name}") from exc
    opened = os.fstat(descriptor)
    if not expected_type(opened.st_mode) or not _same_file(before_open, opened):
        os.close(descriptor)
        raise ContractError(f"collection path component changed before open: {name}")
    return descriptor


def _inspect_regular_file(path: Path) -> tuple[int, str]:
    try:
        before_open = path.lstat()
    except OSError as exc:
        raise ContractError(f"unable to inspect asset safely: {path}") from exc
    if stat.S_ISLNK(before_open.st_mode):
        raise ContractError(f"symlink is forbidden in collection: {path}")
    if not stat.S_ISREG(before_open.st_mode):
        raise ContractError(f"collection entry is not a regular file: {path}")

    try:
        descriptor = os.open(path, _safe_open_flags(directory=False))
    except OSError as exc:
        raise ContractError(f"unable to open asset safely without following links: {path}") from exc

    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or not _same_file(before_open, opened):
            raise ContractError(f"asset changed before hashing: {path}")
        digest = _hash_descriptor(descriptor)
        after_hash = os.fstat(descriptor)
        try:
            current_path = path.lstat()
        except OSError as exc:
            raise ContractError(f"asset changed during hashing: {path}") from exc
        if (
            not _same_file(opened, after_hash)
            or not _same_file(after_hash, current_path)
            or not _same_metadata(opened, after_hash)
        ):
            raise ContractError(f"asset changed during hashing: {path}")
        return after_hash.st_size, digest
    finally:
        os.close(descriptor)


def _same_file(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _same_metadata(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_size == second.st_size
        and first.st_mtime_ns == second.st_mtime_ns
        and first.st_ctime_ns == second.st_ctime_ns
    )


def _role_for_path(relative_path: str) -> str:
    name = PurePosixPath(relative_path).name.lower()
    if name.endswith("-wal"):
        return "sqlite_wal"
    if name.endswith("-shm"):
        return "sqlite_shm"
    return _ROLE_BY_SUFFIX.get(PurePosixPath(name).suffix, "asset")


def _validate_collection_axes(
    *,
    license_status: object,
    platform_qualification: object,
    evidence_role: object,
    lineage_contains_noncommercial: object,
) -> None:
    string_axes = {
        "license_status": license_status,
        "platform_qualification": platform_qualification,
        "evidence_role": evidence_role,
    }
    for field, value in string_axes.items():
        if not isinstance(value, str):
            raise ContractError(f"{field} must be a string")
    if type(lineage_contains_noncommercial) is not bool:
        raise ContractError("lineage_contains_noncommercial must be a bool")


def _validate_manifest(manifest: Mapping[str, object]) -> dict[str, _ExpectedAsset]:
    raw_assets = _validated_manifest_assets(manifest)

    expected: dict[str, _ExpectedAsset] = {}
    manifest_paths: list[str] = []
    for index, raw_asset in enumerate(raw_assets):
        if not isinstance(raw_asset, Mapping):
            raise ContractError(f"manifest asset {index} must be an object")
        if set(raw_asset) != _ASSET_KEYS:
            raise ContractError(f"manifest asset {index} must contain exactly the contract fields")
        path = _validated_asset_path(raw_asset, index)
        if path in expected:
            raise ContractError(f"duplicate manifest asset path: {path}")
        manifest_paths.append(path)
        _validate_asset_metadata(raw_asset, index, path)
        expected[path] = _ExpectedAsset(
            path=path,
            byte_count=_asset_bytes(raw_asset, index),
            sha256=_asset_sha256(raw_asset, index),
        )
    if manifest_paths != sorted(manifest_paths):
        raise ContractError("manifest assets must use canonical sorted path order")
    return expected


def _validated_manifest_assets(manifest: Mapping[str, object]) -> list[object]:
    if not isinstance(manifest, Mapping):
        raise ContractError("manifest must be a JSON object")
    if set(manifest) != _MANIFEST_KEYS:
        raise ContractError(
            "manifest must contain exactly schema_version, collection_id, and assets"
        )
    schema_version = manifest.get("schema_version")
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        raise ContractError(f"manifest schema_version must be {SCHEMA_VERSION}")
    collection_id = manifest.get("collection_id")
    if not isinstance(collection_id, str) or not collection_id:
        raise ContractError("manifest collection_id must be a non-empty string")

    raw_assets = manifest.get("assets")
    if not isinstance(raw_assets, list):
        raise ContractError("manifest assets must be a list")
    return raw_assets


def _validated_asset_path(asset: Mapping[str, object], index: int) -> str:
    raw_path = asset.get("path")
    if not isinstance(raw_path, str):
        raise ContractError(f"manifest asset {index} path must be a string")
    return safe_relative_path(raw_path)


def _asset_bytes(asset: Mapping[str, object], index: int) -> int:
    byte_count = asset.get("bytes")
    if type(byte_count) is not int or byte_count < 0:
        raise ContractError(f"manifest asset {index} bytes must be a non-negative integer")
    return byte_count


def _asset_sha256(asset: Mapping[str, object], index: int) -> str:
    digest = asset.get("sha256")
    if not isinstance(digest, str) or _SHA256_PATTERN.fullmatch(digest) is None:
        raise ContractError(f"manifest asset {index} sha256 must be lowercase hexadecimal")
    return digest


def _validate_asset_metadata(asset: Mapping[str, object], index: int, path: str) -> None:
    role = asset.get("role")
    expected_role = _role_for_path(path)
    if role != expected_role:
        raise ContractError(f"manifest asset {index} role must be {expected_role}")
    _validate_collection_axes(
        license_status=asset.get("license_status"),
        platform_qualification=asset.get("platform_qualification"),
        evidence_role=asset.get("evidence_role"),
        lineage_contains_noncommercial=asset.get("lineage_contains_noncommercial"),
    )
    _asset_bytes(asset, index)
    _asset_sha256(asset, index)
