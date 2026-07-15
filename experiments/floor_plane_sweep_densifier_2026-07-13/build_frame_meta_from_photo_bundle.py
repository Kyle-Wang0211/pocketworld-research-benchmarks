#!/usr/bin/env python3
"""Convert a first-party photo bundle into the structural sweep frame schema.

The conversion is intentionally mechanical: high-resolution intrinsics and the
ARKit camera-to-world transform are copied without refinement.  Each transform
is checked against the independently persisted SfM feed ledger before the frame
is admitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_frame_meta(bundle_path: Path, ledger_path: Path, photos: Path) -> dict:
    bundle = json.loads(bundle_path.read_text())
    ledger_by_name = {}
    for line in ledger_path.read_text().splitlines():
        if not line:
            continue
        row = json.loads(line)
        ledger_by_name[Path(row["jpegPath"]).name] = row

    frames = []
    image_size: tuple[int, int] | None = None
    missing_photos = []
    missing_ledger = []
    maximum_center_error_m = 0.0
    for source in bundle["frames"]:
        name = source["highresFilename"]
        image_path = photos / name
        if not image_path.is_file():
            missing_photos.append(name)
            continue
        ledger = ledger_by_name.get(name)
        if ledger is None:
            missing_ledger.append(name)
            continue
        with Image.open(image_path) as image:
            current_size = image.size
        if image_size is None:
            image_size = current_size
        elif current_size != image_size:
            raise ValueError(
                f"mixed image dimensions: {name} is {current_size}, expected {image_size}"
            )

        intrinsics = source["intrinsics"]
        if len(intrinsics) != 4 or min(float(value) for value in intrinsics) <= 0:
            raise ValueError(f"invalid high-resolution intrinsics for {name}")
        transform = np.asarray(source["cameraTransform"], dtype=np.float64)
        if transform.shape != (16,):
            raise ValueError(f"invalid camera transform for {name}")
        center = transform.reshape(4, 4).T[:3, 3]
        ledger_center = np.asarray(ledger["arkitCameraCenterWorld"], dtype=np.float64)
        center_error = float(np.linalg.norm(center - ledger_center))
        maximum_center_error_m = max(maximum_center_error_m, center_error)
        if center_error > 1e-4:
            raise ValueError(f"pose center mismatch for {name}: {center_error:.9g} m")

        frames.append(
            {
                "name": f"frame_{int(ledger['frameId']):06d}.png",
                "src": name,
                "frame_id": int(ledger["frameId"]),
                "fx": float(intrinsics[0]),
                "fy": float(intrinsics[1]),
                "cx": float(intrinsics[2]),
                "cy": float(intrinsics[3]),
                "extrinsic": [float(value) for value in transform],
            }
        )

    if image_size is None or len(frames) < 3:
        raise ValueError("fewer than three photo-and-ledger-aligned frames")
    frames.sort(key=lambda row: row["frame_id"])
    return {
        "schema": "aether_photo_bundle_frame_meta_v1",
        "capture": bundle.get("captureVersion"),
        "work_w": image_size[0],
        "work_h": image_size[1],
        "frames": frames,
        "validation": {
            "bundle_frames": len(bundle["frames"]),
            "ledger_frames": len(ledger_by_name),
            "admitted_frames": len(frames),
            "missing_photos": missing_photos,
            "missing_ledger": missing_ledger,
            "maximum_pose_center_error_m": maximum_center_error_m,
            "intrinsics_source": "photo_bundle high-resolution intrinsics",
            "pose_source": "photo_bundle cameraTransform cross-checked against sfm ledger",
        },
        "inputs": {
            "photo_bundle": {"path": str(bundle_path), "sha256": sha256(bundle_path)},
            "sfm_feed_ledger": {"path": str(ledger_path), "sha256": sha256(ledger_path)},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photo-bundle", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = build_frame_meta(args.photo_bundle, args.ledger, args.photos)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(json.dumps(document["validation"], sort_keys=True))


if __name__ == "__main__":
    main()
