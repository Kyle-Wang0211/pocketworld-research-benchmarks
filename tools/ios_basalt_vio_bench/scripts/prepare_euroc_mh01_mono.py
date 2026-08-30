#!/usr/bin/env python3
"""Create the strict cam0-only EuRoC MH_01_easy replay manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


DATASET_NAME = "EuRoC_MH_01_easy"
DOMAIN = b"euroc-ordered-dataset-v1\0"


@dataclass(frozen=True)
class FileRecord:
    role: str
    relative_path: str
    byte_count: int
    sha256: str

    def json(self) -> dict[str, object]:
        return {
            "role": self.role,
            "relative_path": self.relative_path,
            "byte_count": self.byte_count,
            "sha256": self.sha256,
        }


def _safe_relative(path: str) -> bool:
    pure = PurePosixPath(path)
    return bool(path) and not pure.is_absolute() and "\\" not in path and all(
        part not in {"", ".", ".."} for part in pure.parts
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record(root: Path, role: str, relative_path: str) -> FileRecord:
    if not _safe_relative(relative_path):
        raise ValueError(f"unsafe relative path: {relative_path}")
    path = root / relative_path
    if not path.is_file():
        raise FileNotFoundError(path)
    return FileRecord(role, relative_path, path.stat().st_size, _sha256_file(path))


def _camera_images(root: Path) -> list[str]:
    index_path = root / "mav0/cam0/data.csv"
    rows: list[str] = []
    previous: int | None = None
    with index_path.open(newline="", encoding="utf-8") as stream:
        for line_number, raw in enumerate(stream, 1):
            if raw.lstrip().startswith("#") or not raw.strip():
                continue
            fields = next(csv.reader([raw]))
            if len(fields) != 2:
                raise ValueError(f"{index_path}:{line_number}: expected timestamp,filename")
            timestamp = int(fields[0].strip())
            filename = fields[1].strip()
            if timestamp < 0 or (previous is not None and timestamp <= previous):
                raise ValueError(f"{index_path}:{line_number}: timestamp regression")
            if not filename or Path(filename).name != filename:
                raise ValueError(f"{index_path}:{line_number}: unsafe filename")
            relative = f"mav0/cam0/data/{filename}"
            if not (root / relative).is_file():
                raise FileNotFoundError(root / relative)
            rows.append(relative)
            previous = timestamp
    if not rows or len(rows) != len(set(rows)):
        raise ValueError("cam0 index is empty or contains duplicate images")
    actual = {
        path.relative_to(root).as_posix()
        for path in (root / "mav0/cam0/data").iterdir()
        if path.is_file()
    }
    if actual != set(rows):
        missing = sorted(set(rows) - actual)
        unindexed = sorted(actual - set(rows))
        raise ValueError(f"cam0 image/index mismatch missing={missing[:3]} unindexed={unindexed[:3]}")
    return rows


def _update_integer(digest: hashlib._Hash, value: int) -> None:
    digest.update(struct.pack(">Q", value & ((1 << 64) - 1)))


def _update_bytes(digest: hashlib._Hash, value: bytes) -> None:
    _update_integer(digest, len(value))
    digest.update(value)


def dataset_identity(records: list[FileRecord]) -> str:
    digest = hashlib.sha256()
    _update_bytes(digest, DOMAIN)
    _update_integer(digest, 1)
    _update_bytes(digest, DATASET_NAME.encode())
    _update_integer(digest, 1)
    for record in records:
        _update_bytes(digest, record.role.encode())
        _update_bytes(digest, record.relative_path.encode())
        _update_integer(digest, record.byte_count)
        _update_bytes(digest, record.sha256.encode())
    return digest.hexdigest()


def build_manifest(root: Path) -> dict[str, object]:
    root = root.resolve()
    fixed = [
        ("camera0_index", "mav0/cam0/data.csv"),
        ("camera0_calibration", "mav0/cam0/sensor.yaml"),
        ("imu_index", "mav0/imu0/data.csv"),
        ("imu_calibration", "mav0/imu0/sensor.yaml"),
        ("ground_truth", "mav0/state_groundtruth_estimate0/data.csv"),
    ]
    records = [_record(root, role, path) for role, path in fixed]
    records.extend(_record(root, "camera_image", path) for path in _camera_images(root))
    records.sort(key=lambda record: record.relative_path)
    return {
        "schema_version": 1,
        "dataset_name": DATASET_NAME,
        "input_camera_count": 1,
        "dataset_sha256": dataset_identity(records),
        "files": [record.json() for record in records],
    }


def write_manifest(root: Path, destination: Path) -> None:
    manifest = build_manifest(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_root", type=Path, help="extracted MH_01_easy directory containing mav0/")
    parser.add_argument("--output", type=Path, help="default: DATASET_ROOT/input_manifest.json")
    args = parser.parse_args()
    destination = args.output or args.dataset_root / "input_manifest.json"
    write_manifest(args.dataset_root, destination)
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
