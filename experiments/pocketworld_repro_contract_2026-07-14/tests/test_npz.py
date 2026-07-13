from __future__ import annotations

import importlib
import io
import os
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


def test_inspect_npz_uses_allow_pickle_false_on_the_open_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspector = _npz_module()
    archive = tmp_path / "descriptor.npz"
    np.savez(archive, values=np.arange(3, dtype=np.int32))
    original_load = inspector.np.load
    observations: list[tuple[bool, bool]] = []

    def tracked_load(file: object, *, allow_pickle: bool) -> object:
        observations.append((isinstance(file, (str, os.PathLike)), allow_pickle))
        return original_load(file, allow_pickle=allow_pickle)

    monkeypatch.setattr(inspector.np, "load", tracked_load)

    inspector.inspect_npz(archive)

    assert observations == [(False, False)]


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
