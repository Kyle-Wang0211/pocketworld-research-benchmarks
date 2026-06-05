#!/usr/bin/env python3
"""Export official DA3 InputProcessor image/tensor caches for a capture bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--source-mode",
        choices=["source_highres", "canonical_source_rgb", "photos_depth"],
        default="source_highres",
        help=(
            "source_highres is the real official path from captured JPEGs; "
            "canonical_source_rgb uses optional lossless RGB sources; photos_depth "
            "audits the runtime tensor boundary from already-preprocessed PNGs."
        ),
    )
    parser.add_argument("--limit", type=int, default=0, help="0 means all frames")
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_input_cache_manifest.json", report)
    write_markdown(args.out_dir / "official_da3_input_cache_manifest_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official_src = args.official_da3_repo / "src"
    sys.path.insert(0, str(official_src))
    from depth_anything_3.utils.io.input_processor import InputProcessor  # type: ignore

    bundle_dir = args.bundle_dir
    input_manifest = read_json(bundle_dir / "da3_input_manifest.json")
    frames = list(input_manifest.get("frames") or [])
    if args.limit and args.limit > 0:
        frames = select_evenly(frames, args.limit)

    processor = InputProcessor()
    image_dir = args.out_dir / f"photos_depth_official_{args.source_mode}"
    tensor_dir = args.out_dir / f"photos_depth_tensor_official_{args.source_mode}"
    image_dir.mkdir(parents=True, exist_ok=True)
    tensor_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for frame in frames:
        row = export_one(
            processor=processor,
            bundle_dir=bundle_dir,
            image_dir=image_dir,
            tensor_dir=tensor_dir,
            frame=frame,
            source_mode=args.source_mode,
            manifest=input_manifest,
        )
        rows.append(row)

    finite_max = [
        row["dart_tensor_compare"]["max_abs_normalized"]
        for row in rows
        if row.get("dart_tensor_compare", {}).get("shape_match") is True
        and row["dart_tensor_compare"].get("max_abs_normalized") is not None
    ]
    exact = bool(finite_max) and max(finite_max) == 0.0
    missing_dart = [
        row["id"]
        for row in rows
        if row.get("dart_tensor_compare", {}).get("status") == "missing_dart_tensor"
    ]
    return {
        "schema_version": "aether_official_da3_input_cache_manifest_v1",
        "date": args.date,
        "bundle_dir": str(bundle_dir),
        "official_da3_repo": str(args.official_da3_repo),
        "source_mode": args.source_mode,
        "sample_count": len(rows),
        "output_dirs": {
            "official_png": str(image_dir),
            "official_tensor_float32_chw": str(tensor_dir),
        },
        "decision": {
            "status": "official_input_cache_exported",
            "dart_tensor_exact_match": exact,
            "dart_tensor_missing_count": len(missing_dart),
            "dart_tensor_max_abs_normalized": max(finite_max) if finite_max else None,
            "interpretation": interpretation(args.source_mode, exact, finite_max),
        },
        "rows": rows,
    }


def export_one(
    *,
    processor: Any,
    bundle_dir: Path,
    image_dir: Path,
    tensor_dir: Path,
    frame: dict[str, Any],
    source_mode: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    frame_id = str(frame["id"])
    process_res = int(frame.get("resize", {}).get("processRes") or manifest.get("processRes") or 504)
    process_res_method = str(
        frame.get("resize", {}).get("processResMethod")
        or manifest.get("processResMethod")
        or "upper_bound_resize"
    )
    source = source_path_for(bundle_dir, frame, source_mode)
    pil_img = processor._load_image(str(source))
    orig_w, orig_h = pil_img.size
    boundary_img = processor._resize_image(pil_img, process_res, process_res_method)
    boundary_w, boundary_h = boundary_img.size
    if process_res_method.endswith("resize"):
        processed_img = processor._make_divisible_by_resize(
            boundary_img,
            processor.PATCH_SIZE,
        )
    elif process_res_method.endswith("crop"):
        processed_img = processor._make_divisible_by_crop(
            boundary_img,
            processor.PATCH_SIZE,
        )
    else:
        raise ValueError(f"Unsupported process_res_method: {process_res_method}")

    tensor = processor._normalize_image(processed_img).detach().cpu().numpy().astype(np.float32)
    image_path = image_dir / f"{safe_filename(frame_id)}.png"
    tensor_path = tensor_dir / f"{safe_filename(frame_id)}.float32_chw.bin"
    processed_img.save(image_path)
    tensor.astype("<f4", copy=False).tofile(tensor_path)

    dart_tensor = bundle_dir / str(frame.get("imageTensorFloat32ChwRelativePath") or "")
    dart_compare = compare_dart_tensor(dart_tensor, tensor)
    return {
        "id": frame_id,
        "source": str(source),
        "source_mode": source_mode,
        "process_res": process_res,
        "process_res_method": process_res_method,
        "patch_size": int(processor.PATCH_SIZE),
        "sizes": {
            "source_wh": [orig_w, orig_h],
            "boundary_wh": [boundary_w, boundary_h],
            "official_output_wh": [processed_img.size[0], processed_img.size[1]],
            "official_tensor_chw": list(tensor.shape),
        },
        "outputs": {
            "official_png": str(image_path),
            "official_tensor_float32_chw": str(tensor_path),
        },
        "dart_tensor_compare": dart_compare,
    }


def source_path_for(bundle_dir: Path, frame: dict[str, Any], source_mode: str) -> Path:
    if source_mode == "photos_depth":
        return bundle_dir / str(frame["depthImageRelativePath"])
    if source_mode == "canonical_source_rgb":
        return bundle_dir / str(
            frame.get("canonicalSourceRgbRelativePath")
            or frame["sourceHighresRelativePath"]
        )
    return bundle_dir / str(frame["sourceHighresRelativePath"])


def compare_dart_tensor(path: Path, official: np.ndarray) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "missing_dart_tensor",
            "dart_tensor_path": str(path),
            "shape_match": False,
        }
    data = np.fromfile(path, dtype="<f4")
    expected = int(np.prod(official.shape))
    if data.size != expected:
        return {
            "status": "shape_mismatch",
            "dart_tensor_path": str(path),
            "dart_values": int(data.size),
            "official_values": expected,
            "shape_match": False,
        }
    dart = data.reshape(official.shape).astype(np.float32)
    diff = np.abs(dart - official)
    max_abs = float(diff.max())
    mean_abs = float(diff.mean())
    return {
        "status": "exact" if max_abs == 0.0 else "different",
        "dart_tensor_path": str(path),
        "shape_match": True,
        "exact": max_abs == 0.0,
        "max_abs_normalized": max_abs,
        "mean_abs_normalized": mean_abs,
        "p95_abs_normalized": float(np.percentile(diff, 95)),
    }


def interpretation(source_mode: str, exact: bool, finite_max: list[float]) -> str:
    if source_mode == "photos_depth":
        return (
            "Official InputProcessor reading photos_depth PNG matches Dart runtime tensor exactly."
            if exact
            else "Runtime tensor boundary differs from official InputProcessor reading the same photos_depth PNG."
        )
    if exact:
        return "Dart-generated runtime tensor is byte-exact with the official source preprocessing chain for sampled frames."
    max_abs = max(finite_max) if finite_max else None
    return (
        f"Dart runtime tensor is not byte-exact with official {source_mode} preprocessing; "
        f"max normalized diff is {max_abs}."
    )


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    lines = [
        "# Official DA3 input cache manifest",
        "",
        f"- source mode: `{report['source_mode']}`",
        f"- status: `{decision['status']}`",
        f"- sample count: `{report['sample_count']}`",
        f"- Dart tensor exact match: `{decision['dart_tensor_exact_match']}`",
        f"- Dart tensor max abs normalized: `{decision['dart_tensor_max_abs_normalized']}`",
        "",
        "## Interpretation",
        "",
        decision["interpretation"],
        "",
        "## Samples",
        "",
        "| frame | source wh | output wh | compare | max abs |",
        "| --- | --- | --- | --- | ---: |",
    ]
    for row in report["rows"]:
        compare = row["dart_tensor_compare"]
        max_abs = compare.get("max_abs_normalized")
        max_text = "" if max_abs is None else f"{max_abs:.6f}"
        lines.append(
            f"| `{row['id']}` | `{row['sizes']['source_wh']}` | "
            f"`{row['sizes']['official_output_wh']}` | `{compare['status']}` | {max_text} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "source_mode": report["source_mode"],
        "sample_count": report["sample_count"],
        "decision": report["decision"],
    }


def select_evenly(items: list[Any], limit: int) -> list[Any]:
    if len(items) <= limit:
        return items
    if limit <= 1:
        return [items[0]]
    indices = sorted({round(i * (len(items) - 1) / (limit - 1)) for i in range(limit)})
    return [items[index] for index in indices]


def safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)


if __name__ == "__main__":
    raise SystemExit(main())
