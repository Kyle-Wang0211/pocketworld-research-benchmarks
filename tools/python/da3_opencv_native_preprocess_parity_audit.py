#!/usr/bin/env python3
"""Compare a cv2-native DA3 preprocess implementation with official InputProcessor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--source-mode",
        choices=["source_highres", "photos_depth", "canonical_source_rgb"],
        default="source_highres",
    )
    parser.add_argument("--limit", type=int, default=32, help="0 means all frames")
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_opencv_native_preprocess_parity_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_opencv_native_preprocess_parity_audit_zh.md",
        report,
    )
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official_src = args.official_da3_repo / "src"
    sys.path.insert(0, str(official_src))
    from depth_anything_3.utils.io.input_processor import InputProcessor  # type: ignore

    bundle_dir = args.bundle_dir
    manifest = read_json(bundle_dir / "da3_input_manifest.json")
    frames = list(manifest.get("frames") or [])
    if args.limit and args.limit > 0:
        frames = select_evenly(frames, args.limit)

    processor = InputProcessor()
    rows = []
    for frame in frames:
        rows.append(compare_one(bundle_dir, frame, manifest, processor, args.source_mode))

    pixel_max = [row["pixel_compare"]["max_abs_uint8"] for row in rows if row["pixel_compare"]["shape_match"]]
    tensor_max = [
        row["tensor_compare"]["max_abs_normalized"]
        for row in rows
        if row["tensor_compare"]["shape_match"]
    ]
    pixel_exact = bool(pixel_max) and max(pixel_max) == 0
    tensor_exact = bool(tensor_max) and max(tensor_max) == 0.0
    return {
        "schema_version": "aether_official_da3_opencv_native_preprocess_parity_audit_v1",
        "date": args.date,
        "bundle_dir": str(bundle_dir),
        "official_da3_repo": str(args.official_da3_repo),
        "source_mode": args.source_mode,
        "sample_count": len(rows),
        "decision": {
            "status": (
                "pass_cv2_native_matches_official_input_processor"
                if pixel_exact and tensor_exact
                else "warning_cv2_native_not_exact_official_input_processor"
            ),
            "pixel_exact": pixel_exact,
            "tensor_exact": tensor_exact,
            "max_abs_uint8": max(pixel_max) if pixel_max else None,
            "max_abs_normalized": max(tensor_max) if tensor_max else None,
            "interpretation": (
                "A native OpenCV/libjpeg path can reproduce official DA3 InputProcessor pixels/tensors for sampled frames."
                if pixel_exact and tensor_exact
                else "The cv2-native path is not yet byte-exact with official DA3 InputProcessor for sampled frames."
            ),
        },
        "opencv": {
            "cv2_version": cv2.__version__,
        },
        "rows": rows,
    }


def compare_one(
    bundle_dir: Path,
    frame: dict[str, Any],
    manifest: dict[str, Any],
    processor: Any,
    source_mode: str,
) -> dict[str, Any]:
    source = source_path_for(bundle_dir, frame, source_mode)
    process_res = int(frame.get("resize", {}).get("processRes") or manifest.get("processRes") or 504)
    process_res_method = str(
        frame.get("resize", {}).get("processResMethod")
        or manifest.get("processResMethod")
        or "upper_bound_resize"
    )
    official_pil = official_processed_image(
        processor,
        source,
        process_res,
        process_res_method,
    )
    official_u8 = np.asarray(official_pil, dtype=np.uint8)
    native_u8 = cv2_native_processed_image(
        source,
        process_res,
        process_res_method,
        patch_size=int(processor.PATCH_SIZE),
    )
    pixel_diff = native_u8.astype(np.int16) - official_u8.astype(np.int16)
    official_tensor = processor._normalize_image(official_pil).detach().cpu().numpy().astype(np.float32)
    native_tensor = (
        processor._normalize_image(Image.fromarray(native_u8))
        .detach()
        .cpu()
        .numpy()
        .astype(np.float32)
    )
    tensor_diff = np.abs(native_tensor - official_tensor)
    pixel_shape_match = official_u8.shape == native_u8.shape
    tensor_shape_match = official_tensor.shape == native_tensor.shape
    return {
        "id": str(frame["id"]),
        "source": str(source),
        "process_res": process_res,
        "process_res_method": process_res_method,
        "official_shape_hwc": list(official_u8.shape),
        "native_shape_hwc": list(native_u8.shape),
        "pixel_compare": {
            "shape_match": pixel_shape_match,
            "exact": pixel_shape_match and bool(np.array_equal(official_u8, native_u8)),
            "max_abs_uint8": int(np.abs(pixel_diff).max()) if pixel_shape_match else None,
            "mean_abs_uint8": float(np.abs(pixel_diff).mean()) if pixel_shape_match else None,
            "nonzero": int((pixel_diff != 0).sum()) if pixel_shape_match else None,
            "total": int(pixel_diff.size) if pixel_shape_match else None,
        },
        "tensor_compare": {
            "shape_match": tensor_shape_match,
            "exact": tensor_shape_match and bool(np.array_equal(official_tensor, native_tensor)),
            "max_abs_normalized": float(tensor_diff.max()) if tensor_shape_match else None,
            "mean_abs_normalized": float(tensor_diff.mean()) if tensor_shape_match else None,
        },
    }


def official_processed_image(
    processor: Any,
    source: Path,
    process_res: int,
    process_res_method: str,
) -> Image.Image:
    pil_img = processor._load_image(str(source))
    pil_img = processor._resize_image(pil_img, process_res, process_res_method)
    if process_res_method.endswith("resize"):
        return processor._make_divisible_by_resize(pil_img, processor.PATCH_SIZE)
    if process_res_method.endswith("crop"):
        return processor._make_divisible_by_crop(pil_img, processor.PATCH_SIZE)
    raise ValueError(f"Unsupported process_res_method: {process_res_method}")


def cv2_native_processed_image(
    source: Path,
    process_res: int,
    process_res_method: str,
    *,
    patch_size: int,
) -> np.ndarray:
    arr = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if arr is None:
        raise ValueError(f"cv2 could not decode {source}")
    arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    height, width = arr.shape[:2]
    arr = boundary_resize(arr, process_res, process_res_method)
    if process_res_method.endswith("resize"):
        return make_divisible_by_resize(arr, patch_size)
    if process_res_method.endswith("crop"):
        return make_divisible_by_crop(arr, patch_size)
    raise ValueError(f"Unsupported process_res_method: {process_res_method}")


def boundary_resize(arr: np.ndarray, target_size: int, method: str) -> np.ndarray:
    height, width = arr.shape[:2]
    if method in ("upper_bound_resize", "upper_bound_crop"):
        side = max(width, height)
    elif method in ("lower_bound_resize", "lower_bound_crop"):
        side = min(width, height)
    else:
        raise ValueError(f"Unsupported resize method: {method}")
    if side == target_size:
        return arr
    scale = target_size / float(side)
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    interpolation = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA
    return cv2.resize(arr, (new_width, new_height), interpolation=interpolation)


def make_divisible_by_resize(arr: np.ndarray, patch_size: int) -> np.ndarray:
    height, width = arr.shape[:2]
    new_width = max(1, nearest_multiple(width, patch_size))
    new_height = max(1, nearest_multiple(height, patch_size))
    if new_width == width and new_height == height:
        return arr
    upscale = new_width > width or new_height > height
    interpolation = cv2.INTER_CUBIC if upscale else cv2.INTER_AREA
    return cv2.resize(arr, (new_width, new_height), interpolation=interpolation)


def make_divisible_by_crop(arr: np.ndarray, patch_size: int) -> np.ndarray:
    height, width = arr.shape[:2]
    new_width = (width // patch_size) * patch_size
    new_height = (height // patch_size) * patch_size
    if new_width == width and new_height == height:
        return arr
    left = (width - new_width) // 2
    top = (height - new_height) // 2
    return arr[top : top + new_height, left : left + new_width]


def nearest_multiple(value: int, patch_size: int) -> int:
    down = (value // patch_size) * patch_size
    up = down + patch_size
    return up if abs(up - value) <= abs(value - down) else down


def source_path_for(bundle_dir: Path, frame: dict[str, Any], source_mode: str) -> Path:
    if source_mode == "photos_depth":
        return bundle_dir / str(frame["depthImageRelativePath"])
    if source_mode == "canonical_source_rgb":
        return bundle_dir / str(
            frame.get("canonicalSourceRgbRelativePath")
            or frame["sourceHighresRelativePath"]
        )
    return bundle_dir / str(frame["sourceHighresRelativePath"])


def select_evenly(items: list[Any], limit: int) -> list[Any]:
    if len(items) <= limit:
        return items
    if limit <= 1:
        return [items[0]]
    indices = sorted({round(index * (len(items) - 1) / (limit - 1)) for index in range(limit)})
    return [items[index] for index in indices]


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    lines = [
        "# Official DA3 OpenCV native preprocess parity audit",
        "",
        f"- status: `{decision['status']}`",
        f"- source mode: `{report['source_mode']}`",
        f"- sample count: `{report['sample_count']}`",
        f"- pixel exact: `{decision['pixel_exact']}`",
        f"- tensor exact: `{decision['tensor_exact']}`",
        f"- max abs uint8: `{decision['max_abs_uint8']}`",
        f"- max abs normalized: `{decision['max_abs_normalized']}`",
        "",
        "## Interpretation",
        "",
        decision["interpretation"],
        "",
        "## Samples",
        "",
        "| frame | pixel exact | tensor exact | max abs uint8 | max abs normalized |",
        "| --- | --- | --- | ---: | ---: |",
    ]
    for row in report["rows"]:
        lines.append(
            f"| `{row['id']}` | `{row['pixel_compare']['exact']}` | "
            f"`{row['tensor_compare']['exact']}` | "
            f"{row['pixel_compare']['max_abs_uint8']} | "
            f"{row['tensor_compare']['max_abs_normalized']:.6f} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "sample_count": report["sample_count"],
        "decision": report["decision"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
