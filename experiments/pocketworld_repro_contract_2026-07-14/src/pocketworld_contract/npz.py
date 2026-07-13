from __future__ import annotations

import hashlib
import math
import os
import stat
import struct
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np

from pocketworld_contract.manifest import ContractError, safe_relative_path

LOCKED_NUMPY_VERSION = "2.4.2"
DEFAULT_MAX_ARCHIVE_BYTES = 640 * 1024 * 1024
DEFAULT_MAX_MEMBERS = 1024
DEFAULT_MAX_TOTAL_METADATA_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_TOTAL_HEADER_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_MEMBER_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_COPY_CHUNK_BYTES = 4 * 1024 * 1024
_MAX_NPY_HEADER_BYTES = 10_000
_MAX_NPY_DIMENSIONS = 64
_SNAPSHOT_MODE = stat.S_IRUSR | stat.S_IWUSR
_ZIP_CLASSIC_EOCD = struct.Struct("<4s4H2LH")
_ZIP_CENTRAL_DIRECTORY_HEADER = struct.Struct("<4s4B4HL2L5H2L")
_ZIP_CENTRAL_DIRECTORY_ENTRY_BYTES = 46
_ZIP_CENTRAL_DIRECTORY_SIGNATURE = b"PK\x01\x02"
_ZIP_CLASSIC_EOCD_SIGNATURE = b"PK\x05\x06"
_ZIP_END_OF_CENTRAL_DIRECTORY_BYTES = 22
_ZIP_MAX_COMMENT_BYTES = 0xFFFF
_ZIP64_LOCATOR_BYTES = 20
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_ZIP64_UINT16_SENTINEL = 0xFFFF
_ZIP64_UINT32_SENTINEL = 0xFFFFFFFF
_ZIP_CREATE_SYSTEM_DOS = 0
_ZIP_CREATE_SYSTEM_UNIX = 3
_ZIP_DOS_DIRECTORY_BIT = 0x10


@dataclass(frozen=True, slots=True)
class _Limits:
    archive_bytes: int
    members: int
    total_metadata_bytes: int
    total_header_bytes: int
    member_bytes: int
    total_bytes: int


@dataclass(frozen=True, slots=True)
class _Member:
    archive_name: str
    array_name: str
    dtype: np.dtype[object]
    shape: tuple[int, ...]
    header_bytes: int
    array_bytes: int


@dataclass(frozen=True, slots=True)
class _ClassicZipDirectory:
    entry_count: int
    central_size: int
    central_offset: int
    eocd_offset: int
    comment: bytes

    @property
    def metadata_bytes(self) -> int:
        return self.central_size + _ZIP_END_OF_CENTRAL_DIRECTORY_BYTES + len(self.comment)


def inspect_npz(  # noqa: PLR0913 - each independent resource budget is caller-controlled.
    path: str | Path,
    *,
    max_archive_bytes: int = DEFAULT_MAX_ARCHIVE_BYTES,
    max_members: int = DEFAULT_MAX_MEMBERS,
    max_total_metadata_bytes: int = DEFAULT_MAX_TOTAL_METADATA_BYTES,
    max_total_header_bytes: int = DEFAULT_MAX_TOTAL_HEADER_BYTES,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> list[dict[str, object]]:
    """Inspect bounded numeric NPZ members from an immutable private snapshot."""
    if np.__version__ != LOCKED_NUMPY_VERSION:
        raise ContractError(
            f"NPZ inspection requires NumPy {LOCKED_NUMPY_VERSION}, found {np.__version__}"
        )
    limits = _validated_limits(
        max_archive_bytes=max_archive_bytes,
        max_members=max_members,
        max_total_metadata_bytes=max_total_metadata_bytes,
        max_total_header_bytes=max_total_header_bytes,
        max_member_bytes=max_member_bytes,
        max_total_bytes=max_total_bytes,
    )

    source_path = Path(path)
    descriptor = _open_regular_no_follow(source_path)
    try:
        source_before = os.fstat(descriptor)
        if source_before.st_size > limits.archive_bytes:
            raise ContractError("NPZ archive exceeds the configured archive size limit")
        try:
            snapshot = _snapshot_source(
                descriptor,
                source_path=source_path,
                source_before=source_before,
                max_archive_bytes=limits.archive_bytes,
            )
            with snapshot:
                result = _inspect_snapshot(snapshot, limits)
        except ContractError:
            raise
        except (
            EOFError,
            KeyError,
            OSError,
            OverflowError,
            RuntimeError,
            SyntaxError,
            UnicodeError,
            ValueError,
            zipfile.BadZipFile,
            zipfile.LargeZipFile,
        ) as exc:
            raise ContractError(f"NPZ archive is corrupt, unsafe, or unreadable: {path}") from exc
        source_after = os.fstat(descriptor)
        if not _same_stable_metadata(source_before, source_after):
            raise ContractError("NPZ source changed during inspection")
    finally:
        os.close(descriptor)
    return result


def _inspect_snapshot(snapshot: BinaryIO, limits: _Limits) -> list[dict[str, object]]:
    snapshot_before = os.fstat(snapshot.fileno())
    members = _preflight_members(snapshot, limits=limits)
    _require_stable_metadata(
        snapshot_before,
        os.fstat(snapshot.fileno()),
        "NPZ snapshot changed during preflight",
    )
    result = _load_numeric_members(snapshot, members)
    _require_stable_metadata(
        snapshot_before,
        os.fstat(snapshot.fileno()),
        "NPZ snapshot changed during inspection",
    )
    return result


def _validated_limits(  # noqa: PLR0913 - mirrors the public security budget surface.
    *,
    max_archive_bytes: int,
    max_members: int,
    max_total_metadata_bytes: int,
    max_total_header_bytes: int,
    max_member_bytes: int,
    max_total_bytes: int,
) -> _Limits:
    values = {
        "max_archive_bytes": max_archive_bytes,
        "max_members": max_members,
        "max_total_metadata_bytes": max_total_metadata_bytes,
        "max_total_header_bytes": max_total_header_bytes,
        "max_member_bytes": max_member_bytes,
        "max_total_bytes": max_total_bytes,
    }
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ContractError(f"NPZ inspection limit {name} must be a positive integer")
    return _Limits(
        archive_bytes=max_archive_bytes,
        members=max_members,
        total_metadata_bytes=max_total_metadata_bytes,
        total_header_bytes=max_total_header_bytes,
        member_bytes=max_member_bytes,
        total_bytes=max_total_bytes,
    )


def _snapshot_source(
    source_descriptor: int,
    *,
    source_path: Path,
    source_before: os.stat_result,
    max_archive_bytes: int,
) -> BinaryIO:
    with tempfile.TemporaryFile(mode="w+b", dir=source_path.parent) as writable_snapshot:
        snapshot_descriptor = writable_snapshot.fileno()
        _prepare_snapshot_descriptor(snapshot_descriptor, source_before)
        source_digest, copied_bytes = _copy_descriptor(
            source_descriptor,
            snapshot_descriptor,
            max_bytes=max_archive_bytes,
        )
        _verify_source_copy(
            source_descriptor,
            source_digest=source_digest,
            source_before=source_before,
            copied_bytes=copied_bytes,
        )
        _verify_snapshot_copy(
            snapshot_descriptor,
            source_digest=source_digest,
            copied_bytes=copied_bytes,
        )
        _require_stable_metadata(
            source_before,
            os.fstat(source_descriptor),
            "NPZ source changed during snapshot verification",
        )
        os.lseek(snapshot_descriptor, 0, os.SEEK_SET)
        return _read_only_duplicate(snapshot_descriptor)


def _prepare_snapshot_descriptor(
    snapshot_descriptor: int,
    source_before: os.stat_result,
) -> None:
    os.fchmod(snapshot_descriptor, _SNAPSHOT_MODE)
    snapshot_created = os.fstat(snapshot_descriptor)
    if not stat.S_ISREG(snapshot_created.st_mode):
        raise ContractError("NPZ snapshot must be a regular file")
    if stat.S_IMODE(snapshot_created.st_mode) != _SNAPSHOT_MODE:
        raise ContractError("NPZ snapshot must have mode 0600")
    if snapshot_created.st_dev != source_before.st_dev:
        raise ContractError("NPZ snapshot must be created on the source volume")


def _verify_source_copy(
    source_descriptor: int,
    *,
    source_digest: str,
    source_before: os.stat_result,
    copied_bytes: int,
) -> None:
    _require_stable_metadata(
        source_before,
        os.fstat(source_descriptor),
        "NPZ source changed during snapshot",
    )
    if copied_bytes != source_before.st_size:
        raise ContractError("NPZ source size changed during snapshot")
    verified_digest, verified_bytes = _hash_descriptor(source_descriptor)
    if verified_bytes != copied_bytes or verified_digest != source_digest:
        raise ContractError("NPZ source digest changed during snapshot")
    _require_stable_metadata(
        source_before,
        os.fstat(source_descriptor),
        "NPZ source changed during snapshot hashing",
    )


def _verify_snapshot_copy(
    snapshot_descriptor: int,
    *,
    source_digest: str,
    copied_bytes: int,
) -> None:
    if os.fstat(snapshot_descriptor).st_size != copied_bytes:
        raise ContractError("NPZ snapshot size differs from the bounded copy")
    snapshot_digest, hashed_bytes = _hash_descriptor(snapshot_descriptor)
    if hashed_bytes != copied_bytes or snapshot_digest != source_digest:
        raise ContractError("NPZ snapshot digest differs from the source copy")


def _read_only_duplicate(descriptor: int) -> BinaryIO:
    reader_descriptor = os.dup(descriptor)
    try:
        return os.fdopen(reader_descriptor, "rb", closefd=True)
    except (OSError, ValueError):
        os.close(reader_descriptor)
        raise


def _copy_descriptor(
    source_descriptor: int,
    destination_descriptor: int,
    *,
    max_bytes: int,
) -> tuple[str, int]:
    os.lseek(source_descriptor, 0, os.SEEK_SET)
    os.lseek(destination_descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    copied_bytes = 0
    while chunk := os.read(source_descriptor, _COPY_CHUNK_BYTES):
        copied_bytes += len(chunk)
        if copied_bytes > max_bytes:
            raise ContractError("NPZ archive exceeds the configured archive size limit")
        digest.update(chunk)
        _write_all(destination_descriptor, chunk)
    return digest.hexdigest(), copied_bytes


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("unable to complete NPZ snapshot write")
        remaining = remaining[written:]


def _hash_descriptor(descriptor: int) -> tuple[str, int]:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    hashed_bytes = 0
    while chunk := os.read(descriptor, _COPY_CHUNK_BYTES):
        hashed_bytes += len(chunk)
        digest.update(chunk)
    return digest.hexdigest(), hashed_bytes


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
    limits: _Limits,
) -> list[_Member]:
    directory = _preflight_classic_directory(stream, limits)
    stream.seek(0)
    try:
        archive = zipfile.ZipFile(stream)
    except zipfile.BadZipFile as exc:
        raise ContractError("NPZ archive is corrupt or is not a ZIP file") from exc
    with archive:
        entries = _bounded_archive_entries(archive, limits, directory)
        validated_entries = _validate_member_entries(entries, limits)
        members = _preflight_validated_members(archive, validated_entries, limits)
    return sorted(members, key=lambda member: member.array_name)


def _preflight_classic_directory(
    stream: BinaryIO,
    limits: _Limits,
) -> _ClassicZipDirectory:
    stream.seek(0, os.SEEK_END)
    archive_size = stream.tell()
    if archive_size < _ZIP_END_OF_CENTRAL_DIRECTORY_BYTES:
        raise ContractError("NPZ archive is corrupt: truncated classic EOCD")

    tail_size = min(
        archive_size,
        _ZIP_END_OF_CENTRAL_DIRECTORY_BYTES + _ZIP_MAX_COMMENT_BYTES,
    )
    tail_start = archive_size - tail_size
    stream.seek(tail_start)
    tail = _read_exact(stream, tail_size, "NPZ classic EOCD search window")
    candidate_offsets = _terminal_eocd_offsets(tail)
    if len(candidate_offsets) != 1:
        raise ContractError("NPZ archive must contain one unique terminal classic EOCD")

    relative_offset = candidate_offsets[0]
    fields = _ZIP_CLASSIC_EOCD.unpack_from(tail, relative_offset)
    directory = _validate_classic_eocd_fields(
        stream,
        fields=fields,
        eocd_offset=tail_start + relative_offset,
        comment=tail[relative_offset + _ZIP_END_OF_CENTRAL_DIRECTORY_BYTES :],
        limits=limits,
    )
    _scan_classic_central_directory(stream, directory)
    return directory


def _terminal_eocd_offsets(tail: bytes) -> list[int]:
    candidates: list[int] = []
    search_offset = 0
    while True:
        offset = tail.find(_ZIP_CLASSIC_EOCD_SIGNATURE, search_offset)
        if offset < 0:
            return candidates
        fixed_end = offset + _ZIP_END_OF_CENTRAL_DIRECTORY_BYTES
        if fixed_end <= len(tail):
            comment_length = struct.unpack_from("<H", tail, fixed_end - 2)[0]
            if fixed_end + comment_length == len(tail):
                candidates.append(offset)
        search_offset = offset + 1


def _validate_classic_eocd_fields(
    stream: BinaryIO,
    *,
    fields: tuple[bytes, int, int, int, int, int, int, int],
    eocd_offset: int,
    comment: bytes,
    limits: _Limits,
) -> _ClassicZipDirectory:
    (
        signature,
        disk_number,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_offset,
        comment_length,
    ) = fields
    if signature != _ZIP_CLASSIC_EOCD_SIGNATURE or comment_length != len(comment):
        raise ContractError("NPZ archive has a forged classic EOCD")
    if _has_zip64_locator(stream, eocd_offset) or _uses_zip64_eocd_sentinel(fields):
        raise ContractError("ZIP64 EOCD records are forbidden for bounded NPZ inspection")
    if disk_number != 0 or central_disk != 0 or disk_entries != total_entries:
        raise ContractError("NPZ archive must use one classic ZIP disk")
    if total_entries > limits.members:
        raise ContractError("NPZ archive exceeds the configured member count limit")
    if total_entries == 0:
        raise ContractError("NPZ archive contains no arrays")

    directory = _ClassicZipDirectory(
        entry_count=total_entries,
        central_size=central_size,
        central_offset=central_offset,
        eocd_offset=eocd_offset,
        comment=comment,
    )
    if directory.metadata_bytes > limits.total_metadata_bytes:
        raise ContractError("NPZ central metadata exceeds the configured limit")
    if central_offset + central_size != eocd_offset:
        raise ContractError("NPZ central directory offset and size do not meet the EOCD boundary")
    minimum_central_bytes = total_entries * _ZIP_CENTRAL_DIRECTORY_ENTRY_BYTES
    if minimum_central_bytes > central_size:
        raise ContractError("NPZ central directory is too small for its declared entry count")
    return directory


def _has_zip64_locator(stream: BinaryIO, eocd_offset: int) -> bool:
    if eocd_offset < _ZIP64_LOCATOR_BYTES:
        return False
    stream.seek(eocd_offset - _ZIP64_LOCATOR_BYTES)
    return stream.read(len(_ZIP64_LOCATOR_SIGNATURE)) == _ZIP64_LOCATOR_SIGNATURE


def _uses_zip64_eocd_sentinel(
    fields: tuple[bytes, int, int, int, int, int, int, int],
) -> bool:
    (
        _signature,
        disk_number,
        central_disk,
        disk_entries,
        total_entries,
        central_size,
        central_offset,
        _comment_length,
    ) = fields
    return _ZIP64_UINT16_SENTINEL in {
        disk_number,
        central_disk,
        disk_entries,
        total_entries,
    } or _ZIP64_UINT32_SENTINEL in {central_size, central_offset}


def _scan_classic_central_directory(
    stream: BinaryIO,
    directory: _ClassicZipDirectory,
) -> None:
    stream.seek(directory.central_offset)
    consumed_bytes = 0
    for _index in range(directory.entry_count):
        if consumed_bytes + _ZIP_CENTRAL_DIRECTORY_ENTRY_BYTES > directory.central_size:
            raise ContractError("NPZ central directory is truncated before an entry header")
        fixed_header = _read_exact(
            stream,
            _ZIP_CENTRAL_DIRECTORY_ENTRY_BYTES,
            "NPZ central directory header",
        )
        fields = _ZIP_CENTRAL_DIRECTORY_HEADER.unpack(fixed_header)
        if fields[0] != _ZIP_CENTRAL_DIRECTORY_SIGNATURE:
            raise ContractError("NPZ central directory has an invalid entry signature")
        filename_bytes, extra_bytes, comment_bytes = fields[12:15]
        disk_number = fields[15]
        local_header_offset = fields[18]
        if (
            _ZIP64_UINT32_SENTINEL in {fields[10], fields[11], local_header_offset}
            or disk_number == _ZIP64_UINT16_SENTINEL
        ):
            raise ContractError("ZIP64 central directory entries are forbidden")
        if disk_number != 0:
            raise ContractError("NPZ central directory entry must use the single archive disk")
        if local_header_offset >= directory.central_offset:
            raise ContractError("NPZ central directory entry has an invalid local-header offset")
        variable_bytes = filename_bytes + extra_bytes + comment_bytes
        entry_bytes = _ZIP_CENTRAL_DIRECTORY_ENTRY_BYTES + variable_bytes
        consumed_bytes += entry_bytes
        if consumed_bytes > directory.central_size:
            raise ContractError("NPZ central directory entry exceeds its declared size")
        stream.seek(variable_bytes, os.SEEK_CUR)
    if consumed_bytes != directory.central_size or stream.tell() != directory.eocd_offset:
        raise ContractError("NPZ central directory count and size declarations disagree")


def _read_exact(stream: BinaryIO, byte_count: int, context: str) -> bytes:
    data = stream.read(byte_count)
    if len(data) != byte_count:
        raise ContractError(f"{context} is truncated")
    return data


def _bounded_archive_entries(
    archive: zipfile.ZipFile,
    limits: _Limits,
    directory: _ClassicZipDirectory,
) -> list[zipfile.ZipInfo]:
    entries = archive.infolist()
    if len(entries) != directory.entry_count or len(entries) > limits.members:
        raise ContractError("NPZ central directory entry count changed after raw preflight")
    if archive.start_dir != directory.central_offset or archive.comment != directory.comment:
        raise ContractError("NPZ central directory identity changed after raw preflight")
    metadata_bytes = _central_directory_metadata_bytes(archive, entries)
    if metadata_bytes != directory.metadata_bytes or metadata_bytes > limits.total_metadata_bytes:
        raise ContractError("NPZ central metadata changed after raw preflight")
    archive_names = [entry.filename for entry in entries]
    if len(archive_names) != len(set(archive_names)):
        raise ContractError("NPZ archive contains duplicate member names")
    if not entries:
        raise ContractError("NPZ archive contains no arrays")
    return entries


def _validate_member_entries(
    entries: list[zipfile.ZipInfo],
    limits: _Limits,
) -> list[tuple[zipfile.ZipInfo, str, str]]:
    validated_entries: list[tuple[zipfile.ZipInfo, str, str]] = []
    array_names: set[str] = set()
    total_member_bytes = 0
    for entry in entries:
        archive_name, array_name = _validate_member_entry(entry)
        if array_name in array_names:
            raise ContractError(f"NPZ archive contains duplicate array names: {array_name}")
        array_names.add(array_name)
        if entry.file_size < 0 or entry.file_size > limits.member_bytes:
            raise ContractError(f"NPZ member exceeds the configured size limit: {array_name}")
        total_member_bytes += entry.file_size
        if total_member_bytes > limits.total_bytes:
            raise ContractError("NPZ members exceed the configured total size limit")
        validated_entries.append((entry, archive_name, array_name))
    return validated_entries


def _preflight_validated_members(
    archive: zipfile.ZipFile,
    entries: list[tuple[zipfile.ZipInfo, str, str]],
    limits: _Limits,
) -> list[_Member]:
    members: list[_Member] = []
    total_header_bytes = 0
    for entry, archive_name, array_name in entries:
        member = _preflight_member(
            archive,
            entry,
            archive_name=archive_name,
            array_name=array_name,
            max_member_bytes=limits.member_bytes,
        )
        total_header_bytes += member.header_bytes
        if total_header_bytes > limits.total_header_bytes:
            raise ContractError("NPZ headers exceed the configured aggregate header limit")
        members.append(member)
    return members


def _central_directory_metadata_bytes(
    archive: zipfile.ZipFile,
    entries: list[zipfile.ZipInfo],
) -> int:
    total = _ZIP_END_OF_CENTRAL_DIRECTORY_BYTES + len(archive.comment)
    for entry in entries:
        encoding = "utf-8" if entry.flag_bits & 0x800 else "cp437"
        try:
            filename_bytes = entry.filename.encode(encoding)
        except UnicodeEncodeError as exc:
            raise ContractError(
                f"NPZ member name has invalid ZIP encoding: {entry.filename!r}"
            ) from exc
        total += (
            _ZIP_CENTRAL_DIRECTORY_ENTRY_BYTES
            + len(filename_bytes)
            + len(entry.extra)
            + len(entry.comment)
        )
    return total


def _validate_member_entry(entry: zipfile.ZipInfo) -> tuple[str, str]:
    archive_name = safe_relative_path(entry.filename)
    if entry.is_dir() or not archive_name.endswith(".npy"):
        raise ContractError(f"NPZ member must be a regular .npy entry: {archive_name}")
    if entry.create_system == _ZIP_CREATE_SYSTEM_UNIX:
        unix_mode = entry.external_attr >> 16
        file_type = stat.S_IFMT(unix_mode)
        if file_type == stat.S_IFLNK:
            raise ContractError(f"NPZ member must not be a Unix symlink: {archive_name}")
        if file_type not in {0, stat.S_IFREG}:
            raise ContractError(f"NPZ member must be a regular file type: {archive_name}")
    elif (
        entry.create_system == _ZIP_CREATE_SYSTEM_DOS
        and entry.external_attr & _ZIP_DOS_DIRECTORY_BIT
    ):
        raise ContractError(f"NPZ member must be a regular file type: {archive_name}")
    array_name = archive_name.removesuffix(".npy")
    if not array_name:
        raise ContractError("NPZ member array name must not be empty")
    return archive_name, array_name


def _preflight_member(
    archive: zipfile.ZipFile,
    entry: zipfile.ZipInfo,
    *,
    archive_name: str,
    array_name: str,
    max_member_bytes: int,
) -> _Member:
    with archive.open(entry, "r") as member_stream:
        shape, dtype, header_bytes = _read_npy_header(member_stream, array_name)
    if dtype.hasobject:
        raise ContractError(f"NPZ member uses forbidden object dtype/pickle payload: {array_name}")
    _validate_shape(shape, array_name)
    nonzero_extent_bytes = math.prod(dimension for dimension in shape if dimension) * dtype.itemsize
    if nonzero_extent_bytes > max_member_bytes:
        raise ContractError(f"NPZ member shape extent exceeds the size limit: {array_name}")
    array_bytes = math.prod(shape) * dtype.itemsize
    if array_bytes > max_member_bytes:
        raise ContractError(f"NPZ member exceeds the configured size limit: {array_name}")
    if header_bytes + array_bytes != entry.file_size:
        raise ContractError(f"NPZ member payload size does not match its header: {array_name}")
    return _Member(
        archive_name=archive_name,
        array_name=array_name,
        dtype=dtype,
        shape=shape,
        header_bytes=header_bytes,
        array_bytes=array_bytes,
    )


def _validate_shape(shape: tuple[int, ...], array_name: str) -> None:
    if len(shape) > _MAX_NPY_DIMENSIONS:
        raise ContractError(f"NPZ member shape exceeds the dimension limit: {array_name}")
    max_dimension = int(np.iinfo(np.intp).max)
    if any(
        isinstance(dimension, bool)
        or not isinstance(dimension, int)
        or dimension < 0
        or dimension > max_dimension
        for dimension in shape
    ):
        raise ContractError(f"NPZ member shape has an invalid dimension: {array_name}")


def _read_npy_header(
    stream: BinaryIO,
    array_name: str,
) -> tuple[tuple[int, ...], np.dtype[object], int]:
    header_start = stream.tell()
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
    return shape, dtype, stream.tell() - header_start


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


def _require_stable_metadata(
    before: os.stat_result,
    after: os.stat_result,
    message: str,
) -> None:
    if not _same_stable_metadata(before, after):
        raise ContractError(message)


def _same_stable_metadata(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
