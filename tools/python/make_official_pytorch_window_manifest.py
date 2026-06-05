#!/usr/bin/env python3
"""Build an official PyTorch DA3 window manifest for fixed-input or high-res parity."""

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
    parser.add_argument(
        "--image-source",
        choices=["photos_depth", "photos_highres", "canonical_source_rgb"],
        default="photos_depth",
        help=(
            "photos_depth uses the APP official-preprocessed 504x280 PNG input and scaled intrinsics; "
            "photos_highres lets official PyTorch do dynamic upper_bound_resize from captured source; "
            "canonical_source_rgb uses an optional lossless RGB source PNG when present."
        ),
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    bundle = read_json(args.capture_dir / "photo_bundle.json")
    input_manifest = maybe_read_json(args.capture_dir / "da3_input_manifest.json")
    windows = read_json(args.capture_dir / "da3_k_windows.json")
    frames_by_id = {str(frame["id"]): frame for frame in bundle.get("frames", [])}
    input_by_id = {str(frame["id"]): frame for frame in input_manifest.get("frames", [])}
    selected_window = find_window(windows, args.window_id)

    rows = [
        build_frame_row(
            frame_id=str(frame_id),
            capture_frame=frames_by_id[str(frame_id)],
            input_frame=input_by_id.get(str(frame_id), {}),
            image_source=args.image_source,
        )
        for frame_id in selected_window.get("frameIDs", [])
    ]

    manifest = {
        "schemaVersion": "pocketworld_official_pytorch_window_manifest_v1",
        "sourceCapture": str(args.capture_dir),
        "sourceWindowID": args.window_id,
        "frameCount": len(rows),
        "imageSource": args.image_source,
        "window": {
            "id": selected_window.get("id"),
            "chunkStartIndex": selected_window.get("chunkStartIndex"),
            "chunkEndIndexExclusive": selected_window.get("chunkEndIndexExclusive"),
            "selectionMode": selected_window.get("selectionMode"),
            "frameIDs": selected_window.get("frameIDs", []),
        },
        "preprocessContract": preprocess_contract(args.image_source),
        "frames": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "out": str(args.out),
                "windowID": args.window_id,
                "imageSource": args.image_source,
                "frameCount": len(rows),
                "first": rows[0] if rows else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_frame_row(
    *,
    frame_id: str,
    capture_frame: dict[str, Any],
    input_frame: dict[str, Any],
    image_source: str,
) -> dict[str, Any]:
    if image_source == "photos_highres":
        image_path = str(
            input_frame.get("sourceHighresRelativePath")
            or f"photos_highres/{capture_frame.get('highresFilename') or capture_frame.get('previewFilename')}"
        )
        fx, fy, cx, cy = intrinsics_fx_fy_cx_cy(capture_frame.get("intrinsics") or [])
        image_width = int(capture_frame.get("imageWidth") or 0)
        image_height = int(capture_frame.get("imageHeight") or 0)
    elif image_source == "canonical_source_rgb":
        image_path = str(
            input_frame.get("canonicalSourceRgbRelativePath")
            or input_frame.get("sourceHighresRelativePath")
            or f"photos_highres/{capture_frame.get('highresFilename') or capture_frame.get('previewFilename')}"
        )
        fx, fy, cx, cy = intrinsics_fx_fy_cx_cy(capture_frame.get("intrinsics") or [])
        image_width = int(capture_frame.get("imageWidth") or 0)
        image_height = int(capture_frame.get("imageHeight") or 0)
    else:
        image_path = str(input_frame.get("depthImageRelativePath") or f"photos_depth/{frame_id}.png")
        fx, fy, cx, cy = scaled_input_intrinsics(capture_frame, input_frame)
        image_width = int(input_frame.get("inputWidth") or 0)
        image_height = int(input_frame.get("inputHeight") or 0)

    return {
        "frameId": frame_id,
        "imagePath": image_path,
        "jpegPath": image_path,
        "cameraExtrinsic4x4": camera_transform_to_opencv_w2c(
            capture_frame["cameraTransform"]
        )
        .reshape(-1)
        .tolist(),
        "cameraIntrinsicFxFyCxCy": [fx, fy, cx, cy],
        "extrinsicConvention": "opencv_w2c",
        "imageWidth": image_width,
        "imageHeight": image_height,
        "sourceHighres": image_source == "photos_highres",
        "sourceCanonicalRgb": image_source == "canonical_source_rgb",
        "sourceFixedDepthInput": image_source == "photos_depth",
    }


def scaled_input_intrinsics(
    capture_frame: dict[str, Any],
    input_frame: dict[str, Any],
) -> tuple[float, float, float, float]:
    fx, fy, cx, cy = intrinsics_fx_fy_cx_cy(capture_frame.get("intrinsics") or [])
    transform = dict(input_frame.get("intrinsicsTransform") or {})
    return (
        fx * float(transform.get("fxScale", 1.0)),
        fy * float(transform.get("fyScale", 1.0)),
        cx * float(transform.get("cxScale", 1.0)) + float(transform.get("cxOffset", 0.0)),
        cy * float(transform.get("cyScale", 1.0)) + float(transform.get("cyOffset", 0.0)),
    )


def intrinsics_fx_fy_cx_cy(values: list[Any]) -> tuple[float, float, float, float]:
    if len(values) == 4:
        fx, fy, cx, cy = [float(value) for value in values]
        return fx, fy, cx, cy
    if len(values) == 9:
        mat = np.asarray(values, dtype=np.float64).reshape(3, 3)
        return float(mat[0, 0]), float(mat[1, 1]), float(mat[0, 2]), float(mat[1, 2])
    raise ValueError(f"unsupported intrinsics length {len(values)}")


def preprocess_contract(image_source: str) -> dict[str, Any]:
    if image_source == "photos_highres":
        return {
            "owner": "DepthAnything3._preprocess_inputs",
            "expectedMethod": "upper_bound_resize",
            "role": "official_dynamic_aspect_ratio_reference",
            "note": "Uses original high-res ARKit intrinsics; official PyTorch rescales intrinsics after resizing.",
        }
    if image_source == "canonical_source_rgb":
        return {
            "owner": "DepthAnything3._preprocess_inputs",
            "expectedMethod": "upper_bound_resize",
            "role": "official_dynamic_aspect_ratio_reference_with_lossless_source_decode",
            "note": (
                "Uses optional canonicalSourceRgbRelativePath when present. This keeps official "
                "PyTorch preprocessing unchanged while moving JPEG decode differences outside "
                "the DA3 parity comparison."
            ),
        }
    return {
        "owner": "PocketWorld official-preprocessed mobile input cache + DepthAnything3._preprocess_inputs",
        "expectedMethod": "already_504x280_patch_aligned_then_upper_bound_resize_no_shape_change",
        "role": "hard CoreML/PyTorch same-input parity for the mobile tensor boundary",
        "note": (
            "Uses photos_depth PNG and intrinsics already scaled by the Dart official "
            "process_res=504 upper_bound_resize + patch-align cache. Official PyTorch "
            "still calls _preprocess_inputs, but this path should not resize 504x280 inputs."
        ),
    }


def find_window(windows: dict[str, Any], window_id: str) -> dict[str, Any]:
    for window in windows.get("windows", []):
        if str(window.get("id")) == window_id:
            return dict(window)
    raise KeyError(f"{window_id} not found in da3_k_windows.json")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def maybe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


if __name__ == "__main__":
    raise SystemExit(main())
