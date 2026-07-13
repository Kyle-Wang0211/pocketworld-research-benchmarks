from __future__ import annotations

import importlib
import io
import os
import stat
import struct
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

if TYPE_CHECKING:
    from types import ModuleType


def _write_marker(path: str) -> str:
    Path(path).write_text("pickle executed", encoding="utf-8")
    return "executed"


class _PickleMarker:
    def __init__(self, marker: Path) -> None:
        self.marker = marker

    def __reduce__(self) -> tuple[object, tuple[str]]:
        return _write_marker, (str(self.marker),)


def _npz_module() -> ModuleType:
    return importlib.import_module("pocketworld_contract.npz")


def _npy_bytes(array: np.ndarray[object, object]) -> bytes:
    stream = io.BytesIO()
    np.save(stream, array, allow_pickle=False)
    return stream.getvalue()


def _npy_header_bytes(*, shape: tuple[int, ...], dtype: np.dtype[object]) -> bytes:
    stream = io.BytesIO()
    np.lib.format.write_array_header_1_0(
        stream,
        {
            "descr": np.lib.format.dtype_to_descr(dtype),
            "fortran_order": False,
            "shape": shape,
        },
    )
    return stream.getvalue()


def _descriptor_identity(descriptor: int) -> tuple[int, int]:
    descriptor_stat = os.fstat(descriptor)
    return descriptor_stat.st_dev, descriptor_stat.st_ino


def _classic_eocd_offset(archive: Path) -> int:
    offset = archive.read_bytes().rfind(b"PK\x05\x06")
    assert offset >= 0
    return offset


def _patch_eocd_u16(archive: Path, field_offset: int, value: int) -> None:
    content = bytearray(archive.read_bytes())
    struct.pack_into("<H", content, _classic_eocd_offset(archive) + field_offset, value)
    archive.write_bytes(content)


def _patch_eocd_u32(archive: Path, field_offset: int, value: int) -> None:
    content = bytearray(archive.read_bytes())
    struct.pack_into("<L", content, _classic_eocd_offset(archive) + field_offset, value)
    archive.write_bytes(content)


def _patch_first_central_u32(archive: Path, field_offset: int, value: int) -> None:
    content = bytearray(archive.read_bytes())
    eocd_offset = _classic_eocd_offset(archive)
    central_offset = struct.unpack_from("<L", content, eocd_offset + 16)[0]
    struct.pack_into("<L", content, central_offset + field_offset, value)
    archive.write_bytes(content)


def _forbid_zipfile_construction(
    inspector: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_zipfile(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ZipFile must not be constructed before the raw EOCD gate passes")

    monkeypatch.setattr(inspector.zipfile, "ZipFile", forbidden_zipfile)


def test_inspect_npz_accepts_numeric_arrays_with_locked_numpy(tmp_path: Path) -> None:
    inspector = _npz_module()
    archive = tmp_path / "numeric.npz"
    np.savez(
        archive,
        points=np.arange(12, dtype=np.float32).reshape(4, 3),
        frame_ids=np.arange(4, dtype=np.int64),
    )

    result = inspector.inspect_npz(archive)

    assert np.__version__ == "2.4.2"
    assert result == [
        {"name": "frame_ids", "dtype": "int64", "shape": [4]},
        {"name": "points", "dtype": "float32", "shape": [4, 3]},
    ]


def test_inspect_npz_rejects_object_dtype_without_unpickling(tmp_path: Path) -> None:
    inspector = _npz_module()
    archive = tmp_path / "payload.npz"
    marker = tmp_path / "unpickle-marker.txt"
    np.savez(archive, payload=np.array([_PickleMarker(marker)], dtype=object))
    assert not marker.exists()

    with pytest.raises(inspector.ContractError, match=r"object|pickle"):
        inspector.inspect_npz(archive)

    assert not marker.exists()


def test_inspect_npz_rejects_symlink_before_opening_payload(tmp_path: Path) -> None:
    inspector = _npz_module()
    target = tmp_path / "target.npz"
    np.savez(target, values=np.arange(3, dtype=np.int32))
    link = tmp_path / "link.npz"
    link.symlink_to(target)

    with pytest.raises(inspector.ContractError, match=r"symlink|regular|safely"):
        inspector.inspect_npz(link)


def test_inspect_npz_rejects_nonregular_path(tmp_path: Path) -> None:
    inspector = _npz_module()
    directory = tmp_path / "directory.npz"
    directory.mkdir()

    with pytest.raises(inspector.ContractError, match=r"regular"):
        inspector.inspect_npz(directory)


def test_inspect_npz_rejects_corrupt_zip(tmp_path: Path) -> None:
    inspector = _npz_module()
    archive = tmp_path / "corrupt.npz"
    archive.write_bytes(b"not a zip archive")

    with pytest.raises(inspector.ContractError, match=r"corrupt|unsafe|zip"):
        inspector.inspect_npz(archive)


def test_inspect_npz_rejects_duplicate_members(tmp_path: Path) -> None:
    inspector = _npz_module()
    archive = tmp_path / "duplicate.npz"
    member = io.BytesIO()
    np.save(member, np.arange(3, dtype=np.int32), allow_pickle=False)
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("values.npy", member.getvalue())
        with pytest.warns(UserWarning, match="Duplicate name"):
            output.writestr("values.npy", member.getvalue())

    with pytest.raises(inspector.ContractError, match=r"duplicate"):
        inspector.inspect_npz(archive)


def test_inspect_npz_rejects_member_path_traversal(tmp_path: Path) -> None:
    inspector = _npz_module()
    archive = tmp_path / "traversal.npz"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("../values.npy", _npy_bytes(np.arange(3, dtype=np.int32)))

    with pytest.raises(inspector.ContractError, match=r"path|relative|traversal|normalized"):
        inspector.inspect_npz(archive)


def test_npz_resource_defaults_are_explicit_and_conservative() -> None:
    inspector = _npz_module()

    assert inspector.DEFAULT_MAX_ARCHIVE_BYTES > 0
    assert 1 <= inspector.DEFAULT_MAX_MEMBERS <= 1024
    assert inspector.DEFAULT_MAX_TOTAL_METADATA_BYTES > 0
    assert inspector.DEFAULT_MAX_TOTAL_HEADER_BYTES > 0
    assert inspector.DEFAULT_MAX_MEMBER_BYTES > 0
    assert inspector.DEFAULT_MAX_TOTAL_BYTES > 0


@pytest.mark.parametrize(
    "limit_name",
    [
        "max_archive_bytes",
        "max_members",
        "max_total_metadata_bytes",
        "max_total_header_bytes",
        "max_member_bytes",
        "max_total_bytes",
    ],
)
def test_inspect_npz_rejects_nonpositive_resource_limits(
    tmp_path: Path,
    limit_name: str,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "limits.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))

    with pytest.raises(inspector.ContractError, match=r"positive|limit"):
        inspector.inspect_npz(archive, **{limit_name: 0})


def test_inspect_npz_rejects_archive_size_before_zip_parsing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "archive-limit.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))

    def forbidden_zip_parse(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("ZIP parsing must not run after the archive-size gate fails")

    monkeypatch.setattr(inspector.zipfile, "ZipFile", forbidden_zip_parse)

    with pytest.raises(inspector.ContractError, match=r"archive|limit|size"):
        inspector.inspect_npz(archive, max_archive_bytes=archive.stat().st_size - 1)


def test_inspect_npz_rejects_declared_member_count_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "declared-member-count.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    _patch_eocd_u16(archive, 8, 3)
    _patch_eocd_u16(archive, 10, 3)
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=r"member|count|limit"):
        inspector.inspect_npz(archive, max_members=2)


def test_inspect_npz_rejects_declared_central_bytes_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "declared-central-size.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    _patch_eocd_u32(archive, 12, 257)
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=r"central|metadata|limit"):
        inspector.inspect_npz(archive, max_total_metadata_bytes=256)


def test_inspect_npz_rejects_forged_declared_count_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "forged-count.npz"
    np.savez(
        archive,
        first=np.arange(3, dtype=np.int32),
        second=np.arange(4, dtype=np.int32),
    )
    _patch_eocd_u16(archive, 8, 1)
    _patch_eocd_u16(archive, 10, 1)
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=r"central|count|size|entry"):
        inspector.inspect_npz(archive)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda content, _offset: content[:-1], r"EOCD|truncat|corrupt"),
        (lambda content, _offset: content + b"trailing-junk", r"EOCD|trailing|comment"),
    ],
)
def test_inspect_npz_rejects_invalid_eocd_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: object,
    message: str,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "invalid-eocd.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    content = archive.read_bytes()
    offset = _classic_eocd_offset(archive)
    assert callable(mutation)
    archive.write_bytes(mutation(content, offset))
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=message):
        inspector.inspect_npz(archive)


def test_inspect_npz_rejects_ambiguous_eocd_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "ambiguous-eocd.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    content = archive.read_bytes()
    offset = _classic_eocd_offset(archive)
    fake_eocd = bytearray(content[offset:])
    struct.pack_into("<H", fake_eocd, 20, len(content) - offset)
    archive.write_bytes(content[:offset] + fake_eocd + content[offset:])
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=r"EOCD|unique|ambiguous"):
        inspector.inspect_npz(archive)


def test_inspect_npz_rejects_multidisk_eocd_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "multidisk.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    _patch_eocd_u16(archive, 4, 1)
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=r"single.disk|multi.disk|disk"):
        inspector.inspect_npz(archive)


def test_inspect_npz_rejects_forged_central_boundary_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "central-boundary.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    content = archive.read_bytes()
    offset = _classic_eocd_offset(archive)
    central_offset = struct.unpack_from("<L", content, offset + 16)[0]
    _patch_eocd_u32(archive, 16, central_offset + 1)
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=r"central|offset|bound|size"):
        inspector.inspect_npz(archive)


def test_inspect_npz_rejects_zip64_sentinel_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "zip64-sentinel.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    _patch_eocd_u32(archive, 12, 0xFFFFFFFF)
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=r"ZIP64|zip64"):
        inspector.inspect_npz(archive)


def test_inspect_npz_rejects_central_zip64_sentinel_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "central-zip64-sentinel.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    _patch_first_central_u32(archive, 20, 0xFFFFFFFF)
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=r"ZIP64|zip64"):
        inspector.inspect_npz(archive)


def test_inspect_npz_rejects_zip64_locator_before_zipfile_construction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "zip64-locator.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    content = archive.read_bytes()
    offset = _classic_eocd_offset(archive)
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, 0, 1)
    archive.write_bytes(content[:offset] + locator + content[offset:])
    _forbid_zipfile_construction(inspector, monkeypatch)

    with pytest.raises(inspector.ContractError, match=r"ZIP64|zip64|locator"):
        inspector.inspect_npz(archive)


def test_inspect_npz_rejects_member_count_before_member_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "member-count.npz"
    empty_array = _npy_bytes(np.empty((0,), dtype=np.float64))
    with zipfile.ZipFile(archive, "w") as output:
        for index in range(3):
            output.writestr(f"empty-{index}.npy", empty_array)

    def forbidden_header(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("NPY headers must not be read after the member-count gate fails")

    monkeypatch.setattr(inspector, "_read_npy_header", forbidden_header)

    with pytest.raises(inspector.ContractError, match=r"member|count|limit"):
        inspector.inspect_npz(archive, max_members=2)


def test_inspect_npz_rejects_2048_zero_length_arrays_under_tiny_byte_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "zero-length-bomb.npz"
    empty_array = _npy_bytes(np.empty((0,), dtype=np.uint8))
    with zipfile.ZipFile(archive, "w") as output:
        for index in range(2048):
            output.writestr(f"empty-{index:04d}.npy", empty_array)

    def forbidden_header(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("member-count and byte gates must precede NPY header parsing")

    monkeypatch.setattr(inspector, "_read_npy_header", forbidden_header)

    with pytest.raises(inspector.ContractError, match=r"member|count|limit|size"):
        inspector.inspect_npz(archive, max_member_bytes=1, max_total_bytes=1)


def test_inspect_npz_rejects_central_metadata_budget_before_member_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "metadata-budget.npz"
    entry = zipfile.ZipInfo(f"{'n' * 240}.npy")
    entry.extra = b"\xfe\xca\xc8\x00" + (b"x" * 200)
    entry.comment = b"c" * 200
    with zipfile.ZipFile(archive, "w") as output:
        output.comment = b"a" * 128
        output.writestr(entry, _npy_bytes(np.empty((0,), dtype=np.uint8)))

    def forbidden_header(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("NPY headers must not be read after the metadata gate fails")

    monkeypatch.setattr(inspector, "_read_npy_header", forbidden_header)

    with pytest.raises(inspector.ContractError, match=r"metadata|central|limit"):
        inspector.inspect_npz(archive, max_total_metadata_bytes=256)


def test_inspect_npz_counts_zero_length_npy_header_toward_member_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "member-bytes.npz"
    empty_array = _npy_bytes(np.empty((0,), dtype=np.uint8))
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("empty.npy", empty_array)

    def forbidden_header(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("member byte limits must be checked before NPY headers")

    monkeypatch.setattr(inspector, "_read_npy_header", forbidden_header)

    with pytest.raises(inspector.ContractError, match=r"member|size|limit"):
        inspector.inspect_npz(
            archive,
            max_member_bytes=len(empty_array) - 1,
            max_total_bytes=len(empty_array) * 2,
        )


def test_inspect_npz_counts_all_uncompressed_member_bytes_before_headers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "total-member-bytes.npz"
    empty_array = _npy_bytes(np.empty((0,), dtype=np.uint8))
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("first.npy", empty_array)
        output.writestr("second.npy", empty_array)

    def forbidden_header(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("total member bytes must be checked before NPY headers")

    monkeypatch.setattr(inspector, "_read_npy_header", forbidden_header)

    with pytest.raises(inspector.ContractError, match=r"total|size|limit"):
        inspector.inspect_npz(
            archive,
            max_member_bytes=len(empty_array),
            max_total_bytes=(len(empty_array) * 2) - 1,
        )


def test_inspect_npz_rejects_aggregate_npy_header_budget_before_array_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "header-budget.npz"
    empty_array = _npy_bytes(np.empty((0,), dtype=np.uint8))
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("first.npy", empty_array)
        output.writestr("second.npy", empty_array)

    def forbidden_load(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("np.load must not run after the aggregate header gate fails")

    monkeypatch.setattr(inspector.np, "load", forbidden_load)

    with pytest.raises(inspector.ContractError, match=r"header|limit"):
        inspector.inspect_npz(
            archive,
            max_member_bytes=len(empty_array),
            max_total_bytes=len(empty_array) * 2,
            max_total_header_bytes=len(empty_array),
        )


@pytest.mark.parametrize("member_type", [stat.S_IFLNK, stat.S_IFIFO])
def test_inspect_npz_rejects_explicit_unix_nonregular_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    member_type: int,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / f"nonregular-{member_type}.npz"
    entry = zipfile.ZipInfo("values.npy")
    entry.create_system = 3
    entry.external_attr = (member_type | 0o600) << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(entry, _npy_bytes(np.arange(3, dtype=np.int32)))

    def forbidden_load(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("np.load must not run for a nonregular ZIP member")

    monkeypatch.setattr(inspector.np, "load", forbidden_load)

    with pytest.raises(inspector.ContractError, match=r"regular|symlink|type"):
        inspector.inspect_npz(archive)


def test_inspect_npz_accepts_unix_member_without_explicit_file_type(tmp_path: Path) -> None:
    inspector = _npz_module()
    archive = tmp_path / "implicit-regular.npz"
    entry = zipfile.ZipInfo("values.npy")
    entry.create_system = 3
    entry.external_attr = 0
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(entry, _npy_bytes(np.arange(3, dtype=np.int32)))

    assert inspector.inspect_npz(archive) == [{"name": "values", "dtype": "int32", "shape": [3]}]


def test_inspect_npz_accepts_zero_length_shape_at_inclusive_limits(tmp_path: Path) -> None:
    inspector = _npz_module()
    archive = tmp_path / "zero-shape.npz"
    empty_array = _npy_bytes(np.empty((2, 0, 3), dtype=np.float32))
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("empty.npy", empty_array)

    assert inspector.inspect_npz(
        archive,
        max_archive_bytes=archive.stat().st_size,
        max_members=1,
        max_total_metadata_bytes=1024,
        max_total_header_bytes=len(empty_array),
        max_member_bytes=len(empty_array),
        max_total_bytes=len(empty_array),
    ) == [{"name": "empty", "dtype": "float32", "shape": [2, 0, 3]}]


def test_inspect_npz_rejects_zero_length_shape_with_unrepresentable_dimension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "unrepresentable-shape.npz"
    header = _npy_header_bytes(
        shape=(0, int(np.iinfo(np.intp).max) + 1),
        dtype=np.dtype(np.float64),
    )
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("empty.npy", header)

    def forbidden_load(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("np.load must not see an unrepresentable zero-length shape")

    monkeypatch.setattr(inspector.np, "load", forbidden_load)

    with pytest.raises(inspector.ContractError, match=r"shape|dimension|limit"):
        inspector.inspect_npz(
            archive,
            max_member_bytes=1024,
            max_total_bytes=1024,
            max_total_header_bytes=1024,
        )


def test_inspect_npz_rejects_zero_length_shape_whose_extent_exceeds_member_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "oversized-zero-shape.npz"
    header = _npy_header_bytes(shape=(0, 1025), dtype=np.dtype(np.uint8))
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("empty.npy", header)

    def forbidden_load(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("np.load must not see a zero shape that bypasses the member limit")

    monkeypatch.setattr(inspector.np, "load", forbidden_load)

    with pytest.raises(inspector.ContractError, match=r"shape|extent|member|limit"):
        inspector.inspect_npz(
            archive,
            max_member_bytes=1024,
            max_total_bytes=1024,
            max_total_header_bytes=1024,
        )


def test_inspect_npz_rejects_truncated_npy_payload_before_array_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "truncated-array.npz"
    header = _npy_header_bytes(shape=(1024,), dtype=np.dtype(np.float64))
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("values.npy", header)

    def forbidden_load(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("np.load must not see a truncated NPY payload")

    monkeypatch.setattr(inspector.np, "load", forbidden_load)

    with pytest.raises(inspector.ContractError, match=r"payload|size|truncated"):
        inspector.inspect_npz(
            archive,
            max_member_bytes=16 * 1024,
            max_total_bytes=16 * 1024,
        )


def test_inspect_npz_rejects_member_size_before_array_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "bounded.npz"
    np.savez(archive, values=np.arange(1024, dtype=np.float32))

    def forbidden_load(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("np.load must not run after the preflight size gate fails")

    monkeypatch.setattr(inspector.np, "load", forbidden_load)

    with pytest.raises(inspector.ContractError, match=r"limit|large|size"):
        inspector.inspect_npz(archive, max_member_bytes=128, max_total_bytes=256)


def test_inspect_npz_uses_allow_pickle_false_on_a_read_only_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "descriptor.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    original_load = inspector.np.load
    source_stat = archive.stat()
    source_identity = (source_stat.st_dev, source_stat.st_ino)
    observations: list[tuple[bool, bool, bool, bool, bool, int]] = []

    def tracked_load(file: object, *, allow_pickle: bool) -> object:
        assert isinstance(file, io.IOBase)
        snapshot_stat = os.fstat(file.fileno())
        observations.append(
            (
                isinstance(file, (str, os.PathLike)),
                allow_pickle,
                _descriptor_identity(file.fileno()) == source_identity,
                file.writable(),
                snapshot_stat.st_dev == source_stat.st_dev,
                stat.S_IMODE(snapshot_stat.st_mode),
            )
        )
        return original_load(file, allow_pickle=allow_pickle)

    monkeypatch.setattr(inspector.np, "load", tracked_load)

    inspector.inspect_npz(archive)

    assert observations == [(False, False, False, False, True, 0o600)]


def test_inspect_npz_never_loads_source_mutated_between_preflight_and_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "preflight-race.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    source_stat = archive.stat()
    source_identity = (source_stat.st_dev, source_stat.st_ino)

    malicious = tmp_path / "malicious.npz"
    oversized_header = _npy_header_bytes(shape=(10**12,), dtype=np.dtype(np.float64))
    with zipfile.ZipFile(malicious, "w") as output:
        output.writestr("values.npy", oversized_header)
    malicious_bytes = malicious.read_bytes()

    original_preflight = inspector._preflight_members  # noqa: SLF001 - synchronized race hook.
    original_load = inspector.np.load
    loaded_from_source: list[bool] = []

    def preflight_then_mutate(*args: object, **kwargs: object) -> object:
        members = original_preflight(*args, **kwargs)
        archive.write_bytes(malicious_bytes)
        return members

    def tracked_load(file: object, *, allow_pickle: bool) -> object:
        assert isinstance(file, io.IOBase)
        uses_source = _descriptor_identity(file.fileno()) == source_identity
        loaded_from_source.append(uses_source)
        if uses_source:
            raise AssertionError("np.load must never read the mutable source descriptor")
        return original_load(file, allow_pickle=allow_pickle)

    monkeypatch.setattr(inspector, "_preflight_members", preflight_then_mutate)
    monkeypatch.setattr(inspector.np, "load", tracked_load)

    with pytest.raises(inspector.ContractError, match=r"changed|mutat|stable"):
        inspector.inspect_npz(archive, max_member_bytes=1024, max_total_bytes=1024)

    assert loaded_from_source == [False]


def test_inspect_npz_rejects_source_mutation_during_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "snapshot-race.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    source_stat = archive.stat()
    source_identity = (source_stat.st_dev, source_stat.st_ino)

    replacement = tmp_path / "replacement.npz"
    np.savez(replacement, values=np.arange(4, dtype=np.int32))
    replacement_bytes = replacement.read_bytes()

    original_read = inspector.os.read
    source_mutated = False

    def read_then_mutate(descriptor: int, count: int) -> bytes:
        nonlocal source_mutated
        chunk = original_read(descriptor, count)
        if not source_mutated and chunk and _descriptor_identity(descriptor) == source_identity:
            archive.write_bytes(replacement_bytes)
            source_mutated = True
        return chunk

    def forbidden_load(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("np.load must not run when the source changes during snapshot")

    monkeypatch.setattr(inspector.os, "read", read_then_mutate)
    monkeypatch.setattr(inspector.np, "load", forbidden_load)

    with pytest.raises(inspector.ContractError, match=r"changed|mutat|stable"):
        inspector.inspect_npz(archive)

    assert source_mutated


def test_inspect_npz_rejects_source_metadata_change_during_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "mutable.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    original_load = inspector._load_numeric_members  # noqa: SLF001 - mutation hook under test.

    def load_then_mutate(*args: object, **kwargs: object) -> object:
        result = original_load(*args, **kwargs)
        with archive.open("ab") as stream:
            stream.write(b"mutation")
        return result

    monkeypatch.setattr(inspector, "_load_numeric_members", load_then_mutate)

    with pytest.raises(inspector.ContractError, match=r"changed|mutat|stable"):
        inspector.inspect_npz(archive)
