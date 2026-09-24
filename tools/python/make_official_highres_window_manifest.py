#!/usr/bin/env python3
"""Build an official PyTorch manifest that points to high-res capture images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from da3_mac_window_export import camera_transform_to_opencv_w2c


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_000")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    bundle = read_json(args.capture_dir / "photo_bundle.json")
    windows = read_json(args.capture_dir / "da3_k_windows.json")
    frames_by_id = {str(frame["id"]): frame for frame in bundle.get("frames", [])}
    selected_window = None
    for window in windows.get("windows", []):
        if str(window.get("id")) == args.window_id:
            selected_window = window
            break
    if selected_window is None:
        raise KeyError(f"{args.window_id} not found in {args.capture_dir / 'da3_k_windows.json'}")

    rows = []
    for frame_id in [str(value) for value in selected_window.get("frameIDs", [])]:
        frame = frames_by_id[frame_id]
        highres_name = str(frame.get("highresFilename") or frame.get("previewFilename"))
        if not highres_name:
            raise ValueError(f"{frame_id} has no highres filename")
        intrinsics = frame.get("intrinsics") or []
        if len(intrinsics) == 4:
            fx, fy, cx, cy = [float(value) for value in intrinsics]
        elif len(intrinsics) == 9:
            mat = np.asarray(intrinsics, dtype=np.float64).reshape(3, 3)
            fx, fy, cx, cy = float(mat[0, 0]), float(mat[1, 1]), float(mat[0, 2]), float(mat[1, 2])
        else:
            raise ValueError(f"{frame_id} has unsupported intrinsics length {len(intrinsics)}")
        rows.append(
            {
                "frameId": frame_id,
                "jpegPath": f"photos_highres/{highres_name}",
                "cameraExtrinsic4x4": camera_transform_to_opencv_w2c(frame["cameraTransform"]).reshape(-1).tolist(),
                "cameraIntrinsicFxFyCxCy": [fx, fy, cx, cy],
                "extrinsicConvention": "opencv_w2c",
                "imageWidth": int(frame.get("imageWidth") or 0),
                "imageHeight": int(frame.get("imageHeight") or 0),
                "sourceHighres": True,
            }
        )

    manifest = {
        "schemaVersion": "pocketworld_official_pytorch_highres_manifest_v1",
        "sourceCapture": str(args.capture_dir),
        "windowID": args.window_id,
        "frameCount": len(rows),
        "imageSource": "photos_highres",
        "preprocessContract": {
            "owner": "DepthAnything3._preprocess_inputs",
            "expectedMethod": "upper_bound_resize",
            "note": "Intrinsics are original high-res ARKit intrinsics. Official PyTorch input_processor rescales them after resizing.",
        },
        "frames": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "frameCount": len(rows), "first": rows[0]}, ensure_ascii=False, indent=2))
    return 0


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


if __name__ == "__main__":
    raise SystemExit(main())
