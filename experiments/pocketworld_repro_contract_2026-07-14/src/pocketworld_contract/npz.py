from __future__ import annotations

import math
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

from pocketworld_contract.manifest import ContractError, safe_relative_path

LOCKED_NUMPY_VERSION = "2.4.2"
DEFAULT_MAX_MEMBER_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_NPY_HEADER_BYTES = 10_000


@dataclass(frozen=True, slots=True)
class _Member:
    archive_name: str
    array_name: str
    dtype: np.dtype[object]
    shape: tuple[int, ...]
    array_bytes: int


def inspect_npz(
    path: str | Path,
    *,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> list[dict[str, object]]:
    """Inspect numeric NPZ members through one stable, no-follow file descriptor."""
    if np.__version__ != LOCKED_NUMPY_VERSION:
        raise ContractError(
            f"NPZ inspection requires NumPy {LOCKED_NUMPY_VERSION}, found {np.__version__}"
        )
    if max_member_bytes <= 0 or max_total_bytes <= 0:
        raise ContractError("NPZ inspection size limits must be positive")

    descriptor = _open_regular_no_follow(Path(path))
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            before = os.fstat(stream.fileno())
            try:
                members = _preflight_members(
                    stream,
                    max_member_bytes=max_member_bytes,
                    max_total_bytes=max_total_bytes,
                )
                result = _load_numeric_members(stream, members)
            except ContractError:
                raise
            except (EOFError, KeyError, OSError, RuntimeError, UnicodeError, ValueError) as exc:
                raise ContractError(
                    f"NPZ archive is corrupt, unsafe, or unreadable: {path}"
                ) from exc
            after = os.fstat(stream.fileno())
            if not _same_stable_metadata(before, after):
                raise ContractError("NPZ source changed during inspection")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return result


def _open_regular_no_follow(path: Path) -> int:
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise ContractError("platform cannot safely reject NPZ symlinks")
    flags = os.O_RDONLY | no_follow
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ContractError(f"NPZ path is a symlink or cannot be opened safely: {path}") from exc
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode):
        os.close(descriptor)
        raise ContractError(f"NPZ path must be a regular file: {path}")
    return descriptor


def _preflight_members(
    stream: BinaryIO,
    *,
    max_member_bytes: int,
    max_total_bytes: int,
) -> list[_Member]:
    stream.seek(0)
    try:
        archive = zipfile.ZipFile(stream)
    except zipfile.BadZipFile as exc:
        raise ContractError("NPZ archive is corrupt or is not a ZIP file") from exc
    with archive:
        entries = archive.infolist()
        archive_names = [entry.filename for entry in entries]
        if len(archive_names) != len(set(archive_names)):
            raise ContractError("NPZ archive contains duplicate member names")
        if not entries:
            raise ContractError("NPZ archive contains no arrays")

        members: list[_Member] = []
        array_names: set[str] = set()
        total_array_bytes = 0
        for entry in entries:
            member = _preflight_member(
                archive,
                entry,
                array_names=array_names,
                max_member_bytes=max_member_bytes,
            )
            total_array_bytes += member.array_bytes
            if total_array_bytes > max_total_bytes:
                raise ContractError("NPZ arrays exceed the configured total size limit")
            members.append(member)
    return sorted(members, key=lambda member: member.array_name)


def _preflight_member(
    archive: zipfile.ZipFile,
    entry: zipfile.ZipInfo,
    *,
    array_names: set[str],
    max_member_bytes: int,
) -> _Member:
    archive_name = safe_relative_path(entry.filename)
    if entry.is_dir() or not archive_name.endswith(".npy"):
        raise ContractError(f"NPZ member must be a regular .npy entry: {archive_name}")
    array_name = archive_name.removesuffix(".npy")
    if not array_name or array_name in array_names:
        raise ContractError(f"NPZ archive contains duplicate array names: {array_name}")
    array_names.add(array_name)
    if entry.file_size > max_member_bytes + _MAX_NPY_HEADER_BYTES:
        raise ContractError(f"NPZ member exceeds the configured size limit: {array_name}")
    with archive.open(entry, "r") as member_stream:
        shape, dtype = _read_npy_header(member_stream, array_name)
    array_bytes = math.prod(shape) * dtype.itemsize
    if dtype.hasobject:
        raise ContractError(f"NPZ member uses forbidden object dtype/pickle payload: {array_name}")
    if array_bytes > max_member_bytes:
        raise ContractError(f"NPZ member exceeds the configured size limit: {array_name}")
    return _Member(
        archive_name=archive_name,
        array_name=array_name,
        dtype=dtype,
        shape=shape,
        array_bytes=array_bytes,
    )


def _read_npy_header(stream: BinaryIO, array_name: str) -> tuple[tuple[int, ...], np.dtype[object]]:
    version = np.lib.format.read_magic(stream)
    if version == (1, 0):
        shape, _fortran_order, dtype = np.lib.format.read_array_header_1_0(
            stream,
            max_header_size=_MAX_NPY_HEADER_BYTES,
        )
    elif version == (2, 0):
        shape, _fortran_order, dtype = np.lib.format.read_array_header_2_0(
            stream,
            max_header_size=_MAX_NPY_HEADER_BYTES,
        )
    else:
        raise ContractError(f"unsupported NPY format version {version!r}: {array_name}")
    return shape, dtype


def _load_numeric_members(
    stream: BinaryIO,
    members: list[_Member],
) -> list[dict[str, object]]:
    stream.seek(0)
    with np.load(stream, allow_pickle=False) as archive:
        if sorted(archive.files) != [member.array_name for member in members]:
            raise ContractError("NPZ member index differs from the preflight inventory")
        result: list[dict[str, object]] = []
        for member in members:
            array = archive[member.array_name]
            if array.dtype.hasobject:
                raise ContractError(
                    f"NPZ member uses forbidden object dtype/pickle payload: {member.array_name}"
                )
            if array.dtype != member.dtype or array.shape != member.shape:
                raise ContractError(f"NPZ member changed after preflight: {member.array_name}")
            if array.nbytes != member.array_bytes:
                raise ContractError(f"NPZ member size changed after preflight: {member.array_name}")
            result.append(
                {
                    "name": member.array_name,
                    "dtype": str(array.dtype),
                    "shape": list(array.shape),
                }
            )
            del array
    return result


def _same_stable_metadata(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
