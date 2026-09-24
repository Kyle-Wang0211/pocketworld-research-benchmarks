#!/usr/bin/env python3
"""Compare Dart DA3 input tensors against official DA3 InputProcessor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


MEAN = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)[:, None, None]
STD = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)[:, None, None]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=32, help="0 means all frames")
    parser.add_argument(
        "--official-source",
        choices=["source_highres", "photos_depth", "canonical_source_rgb"],
        default="source_highres",
        help=(
            "source_highres audits the full official PIL/OpenCV preprocessing chain. "
            "photos_depth audits the product/runtime tensor boundary using already "
            "official-preprocessed PNGs. canonical_source_rgb uses optional lossless "
            "source PNGs when present."
        ),
    )
    parser.add_argument(
        "--canonical-source-dir",
        type=Path,
        default=None,
        help=(
            "Optional directory containing <frame-id>.png canonical RGB sources. "
            "Only used with --official-source canonical_source_rgb."
        ),
    )
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_preprocess_pixel_parity_audit.json", report)
    write_markdown(args.out_dir / "official_da3_preprocess_pixel_parity_audit_zh.md", report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    official_src = args.official_da3_repo / "src"
    sys.path.insert(0, str(official_src))
    from depth_anything_3.utils.io.input_processor import InputProcessor  # type: ignore

    bundle_dir = args.bundle_dir
    manifest = json.loads((bundle_dir / "da3_input_manifest.json").read_text())
    frames = list(manifest.get("frames") or [])
    if args.limit and args.limit > 0:
        frames = select_evenly(frames, args.limit)

    processor = InputProcessor()
    rows = []
    for frame in frames:
        source = source_path_for(
            bundle_dir,
            frame,
            args.official_source,
            args.canonical_source_dir,
        )
        dart_path = bundle_dir / str(frame["depthImageRelativePath"])
        dart_tensor_rel = frame.get("imageTensorFloat32ChwRelativePath")
        dart_tensor_path = bundle_dir / str(dart_tensor_rel) if dart_tensor_rel else None
        dart_codec = image_format(dart_path)
        process_res = int(frame.get("resize", {}).get("processRes") or manifest.get("processRes") or 504)
        process_res_method = str(
            frame.get("resize", {}).get("processResMethod")
            or manifest.get("processResMethod")
            or "upper_bound_resize"
        )
        official_tensor, _, _ = processor(
            image=[str(source)],
            process_res=process_res,
            process_res_method=process_res_method,
            num_workers=1,
            sequential=True,
        )
        official = official_tensor[0].detach().cpu().numpy().astype(np.float32)
        if dart_tensor_path and dart_tensor_path.exists():
            dart = read_float32_chw(
                dart_tensor_path,
                shape=official.shape,
            )
            dart_kind = "float32_chw_tensor"
        else:
            dart = normalize_pil_rgb(dart_path)
            dart_kind = "png_normalized_fallback"
        shape_match = list(official.shape) == list(dart.shape)
        if shape_match:
            abs_diff = np.abs(official - dart)
            max_abs = float(abs_diff.max())
            mean_abs = float(abs_diff.mean())
            p95_abs = float(np.percentile(abs_diff, 95))
        else:
            max_abs = mean_abs = p95_abs = float("nan")
        rows.append(
            {
                "id": frame.get("id"),
                "source": str(source),
                "official_source_mode": args.official_source,
                "dart_path": str(dart_path),
                "dart_tensor_path": str(dart_tensor_path) if dart_tensor_path else None,
                "dart_input_kind": dart_kind,
                "dart_codec": dart_codec,
                "manifest_codec": frame.get("resize", {}).get("codec"),
                "manifest_lossless": frame.get("resize", {}).get("lossless"),
                "manifest_tensor": frame.get("tensor"),
                "official_chw": list(official.shape),
                "dart_chw": list(dart.shape),
                "shape_match": shape_match,
                "max_abs_normalized": max_abs,
                "mean_abs_normalized": mean_abs,
                "p95_abs_normalized": p95_abs,
            }
        )

    shape_failures = [row for row in rows if not row["shape_match"]]
    tensor_failures = [
        row
        for row in rows
        if row["dart_input_kind"] != "float32_chw_tensor"
        or not row.get("dart_tensor_path")
    ]
    png_codec_failures = [
        row
        for row in rows
        if row["dart_codec"] != "PNG"
        or row.get("manifest_codec") != "png"
        or row.get("manifest_lossless") is not True
    ]
    finite_max = [
        row["max_abs_normalized"]
        for row in rows
        if np.isfinite(row["max_abs_normalized"])
    ]
    finite_mean = [
        row["mean_abs_normalized"]
        for row in rows
        if np.isfinite(row["mean_abs_normalized"])
    ]
    exact_pixel_match = bool(finite_max) and max(finite_max) == 0.0
    status = (
        "fail_shape_or_tensor_cache"
        if shape_failures or tensor_failures
        else "warning_tensor_not_exact_official_input_processor"
        if not exact_pixel_match
        else "pass_exact_tensor_parity"
    )
    return {
        "schema_version": "aether_official_da3_preprocess_pixel_parity_audit_v1",
        "date": args.date,
        "bundle_dir": str(bundle_dir),
        "official_da3_repo": str(args.official_da3_repo),
        "official_source_mode": args.official_source,
        "sample_count": len(rows),
        "decision": {
            "status": status,
            "shape_match": not shape_failures,
            "tensor_cache": not tensor_failures,
            "png_lossless_cache": not png_codec_failures,
            "exact_tensor_match": exact_pixel_match,
            "max_abs_normalized": max(finite_max) if finite_max else None,
            "mean_abs_normalized_mean": float(np.mean(finite_mean)) if finite_mean else None,
            "hard_gap": (
                "Dart now feeds native from a pre-normalized float32 CHW tensor cache and shape parity holds, "
                "but tensor values are not yet byte-exact with official PIL/OpenCV preprocessing."
            )
            if not shape_failures and not tensor_failures and not exact_pixel_match
            else None,
        },
        "rows": rows,
    }


def normalize_pil_rgb(path: Path) -> np.ndarray:
    arr = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    chw = arr.transpose(2, 0, 1)
    return (chw - MEAN) / STD


def source_path_for(
    bundle_dir: Path,
    frame: dict[str, Any],
    official_source: str,
    canonical_source_dir: Path | None,
) -> Path:
    if official_source == "photos_depth":
        return bundle_dir / str(frame["depthImageRelativePath"])
    if official_source == "canonical_source_rgb":
        if canonical_source_dir is not None:
            candidate = canonical_source_dir / f"{frame['id']}.png"
            if candidate.exists():
                return candidate
        return bundle_dir / str(
            frame.get("canonicalSourceRgbRelativePath")
            or frame["sourceHighresRelativePath"]
        )
    return bundle_dir / str(frame["sourceHighresRelativePath"])


def read_float32_chw(path: Path, shape: tuple[int, ...]) -> np.ndarray:
    expected = int(np.prod(shape))
    data = np.fromfile(path, dtype="<f4")
    if data.size != expected:
        return data.astype(np.float32)
    return data.reshape(shape).astype(np.float32)


def image_format(path: Path) -> str | None:
    with Image.open(path) as img:
        return img.format


def select_evenly(items: list[Any], limit: int) -> list[Any]:
    if len(items) <= limit:
        return items
    if limit <= 1:
        return [items[0]]
    indices = sorted({round(i * (len(items) - 1) / (limit - 1)) for i in range(limit)})
    return [items[i] for i in indices]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    lines = [
        "# Official DA3 preprocess pixel parity audit",
        "",
        f"- status: `{decision['status']}`",
        f"- official source mode: `{report['official_source_mode']}`",
        f"- sampled frames: `{report['sample_count']}`",
        f"- shape match: `{decision['shape_match']}`",
        f"- tensor cache: `{decision['tensor_cache']}`",
        f"- PNG lossless cache: `{decision['png_lossless_cache']}`",
        f"- exact tensor match: `{decision['exact_tensor_match']}`",
        f"- max abs normalized diff: `{decision['max_abs_normalized']}`",
        "",
        "## Interpretation",
        "",
        "Dart now stores DA3's runtime input as pre-normalized float32 CHW tensors, so native PNG decode is no longer part of the official image-only path.",
        "This audit still treats official preprocessing parity as unproven unless every sampled normalized tensor value matches exactly.",
        "",
        "## Samples",
        "",
        "| frame | input | codec | shape | max abs | mean abs |",
        "| --- | --- | --- | --- | ---: | ---: |",
    ]
    for row in report["rows"]:
        lines.append(
            f"| `{row['id']}` | `{row['dart_input_kind']}` | `{row['dart_codec']}` | `{row['dart_chw']}` | "
            f"{row['max_abs_normalized']:.6f} | {row['mean_abs_normalized']:.6f} |"
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
