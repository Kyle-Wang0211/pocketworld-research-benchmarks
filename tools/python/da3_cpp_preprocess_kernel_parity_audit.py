#!/usr/bin/env python3
"""Compare the C++ DA3 preprocess kernel with official DA3 InputProcessor."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--official-da3-repo", type=Path, required=True)
    parser.add_argument("--cpp-cli", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=32, help="0 means all frames")
    parser.add_argument("--date", default="2026-06-05")
    args = parser.parse_args()

    report = build_report(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "official_da3_cpp_preprocess_kernel_parity_audit.json", report)
    write_markdown(
        args.out_dir / "official_da3_cpp_preprocess_kernel_parity_audit_zh.md",
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
    cache_dir = args.out_dir / "cpp_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = [
        compare_one(
            frame=frame,
            bundle_dir=bundle_dir,
            manifest=manifest,
            processor=processor,
            cpp_cli=args.cpp_cli,
            cache_dir=cache_dir,
        )
        for frame in frames
    ]

    pixel_max = [
        row["pixel_compare"]["max_abs_uint8"]
        for row in rows
        if row["pixel_compare"]["shape_match"]
    ]
    tensor_max = [
        row["tensor_compare"]["max_abs_normalized"]
        for row in rows
        if row["tensor_compare"]["shape_match"]
    ]
    pixel_exact = bool(pixel_max) and max(pixel_max) == 0
    tensor_exact = bool(tensor_max) and max(tensor_max) == 0.0
    return {
        "schema_version": "aether_official_da3_cpp_preprocess_kernel_parity_audit_v1",
        "date": args.date,
        "bundle_dir": str(bundle_dir),
        "official_da3_repo": str(args.official_da3_repo),
        "cpp_cli": str(args.cpp_cli),
        "sample_count": len(rows),
        "decision": {
            "status": (
                "pass_cpp_kernel_matches_official_input_processor"
                if pixel_exact and tensor_exact
                else "warning_cpp_kernel_not_exact_official_input_processor"
            ),
            "pixel_exact": pixel_exact,
            "tensor_exact": tensor_exact,
            "max_abs_uint8": max(pixel_max) if pixel_max else None,
            "max_abs_normalized": max(tensor_max) if tensor_max else None,
            "interpretation": (
                "The C++ OpenCV/libjpeg kernel reproduces official DA3 InputProcessor pixels/tensors for sampled frames."
                if pixel_exact and tensor_exact
                else "The C++ kernel is not yet byte-exact with official DA3 InputProcessor."
            ),
        },
        "rows": rows,
    }


def compare_one(
    *,
    frame: dict[str, Any],
    bundle_dir: Path,
    manifest: dict[str, Any],
    processor: Any,
    cpp_cli: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    frame_id = str(frame["id"])
    source = bundle_dir / str(frame["sourceHighresRelativePath"])
    process_res = int(frame.get("resize", {}).get("processRes") or manifest.get("processRes") or 504)
    process_res_method = str(
        frame.get("resize", {}).get("processResMethod")
        or manifest.get("processResMethod")
        or "upper_bound_resize"
    )
    patch_size = int(frame.get("resize", {}).get("patchSize") or manifest.get("patchSize") or 14)
    out_png = cache_dir / f"{safe_filename(frame_id)}.png"
    out_tensor = cache_dir / f"{safe_filename(frame_id)}.float32_chw.bin"
    run = subprocess.run(
        [
            str(cpp_cli),
            "--input",
            str(source),
            "--out-png",
            str(out_png),
            "--out-tensor",
            str(out_tensor),
            "--process-res",
            str(process_res),
            "--process-res-method",
            process_res_method,
            "--patch-size",
            str(patch_size),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if run.returncode != 0:
        return {
            "id": frame_id,
            "source": str(source),
            "cpp_returncode": run.returncode,
            "cpp_stdout": run.stdout,
            "cpp_stderr": run.stderr,
            "pixel_compare": {"shape_match": False},
            "tensor_compare": {"shape_match": False},
        }

    official_pil = processor._load_image(str(source))
    official_pil = processor._resize_image(official_pil, process_res, process_res_method)
    official_pil = processor._make_divisible_by_resize(official_pil, processor.PATCH_SIZE)
    official_u8 = np.asarray(official_pil, dtype=np.uint8)
    cpp_u8 = np.asarray(Image.open(out_png).convert("RGB"), dtype=np.uint8)
    pixel_shape = official_u8.shape == cpp_u8.shape
    pixel_abs = np.abs(cpp_u8.astype(np.int16) - official_u8.astype(np.int16))

    official_tensor = processor._normalize_image(official_pil).detach().cpu().numpy().astype(np.float32)
    cpp_tensor = np.fromfile(out_tensor, dtype="<f4")
    tensor_shape = cpp_tensor.size == int(np.prod(official_tensor.shape))
    if tensor_shape:
        cpp_tensor = cpp_tensor.reshape(official_tensor.shape).astype(np.float32)
        tensor_abs = np.abs(cpp_tensor - official_tensor)
    else:
        tensor_abs = np.asarray([], dtype=np.float32)
    return {
        "id": frame_id,
        "source": str(source),
        "cpp_returncode": run.returncode,
        "cpp_stdout": run.stdout.strip(),
        "process_res": process_res,
        "process_res_method": process_res_method,
        "patch_size": patch_size,
        "official_shape_hwc": list(official_u8.shape),
        "cpp_shape_hwc": list(cpp_u8.shape),
        "pixel_compare": {
            "shape_match": pixel_shape,
            "exact": pixel_shape and bool(np.array_equal(cpp_u8, official_u8)),
            "max_abs_uint8": int(pixel_abs.max()) if pixel_shape else None,
            "mean_abs_uint8": float(pixel_abs.mean()) if pixel_shape else None,
            "nonzero": int((pixel_abs != 0).sum()) if pixel_shape else None,
            "total": int(pixel_abs.size) if pixel_shape else None,
        },
        "tensor_compare": {
            "shape_match": tensor_shape,
            "exact": tensor_shape and bool(np.array_equal(cpp_tensor, official_tensor)),
            "max_abs_normalized": float(tensor_abs.max()) if tensor_shape else None,
            "mean_abs_normalized": float(tensor_abs.mean()) if tensor_shape else None,
        },
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    decision = report["decision"]
    lines = [
        "# Official DA3 C++ preprocess kernel parity audit",
        "",
        f"- status: `{decision['status']}`",
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
        max_abs_norm = row["tensor_compare"].get("max_abs_normalized")
        max_abs_norm_text = "" if max_abs_norm is None else f"{max_abs_norm:.6f}"
        lines.append(
            f"| `{row['id']}` | `{row['pixel_compare'].get('exact')}` | "
            f"`{row['tensor_compare'].get('exact')}` | "
            f"{row['pixel_compare'].get('max_abs_uint8')} | "
            f"{max_abs_norm_text} |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "sample_count": report["sample_count"],
        "decision": report["decision"],
    }


def select_evenly(items: list[Any], limit: int) -> list[Any]:
    if len(items) <= limit:
        return items
    if limit <= 1:
        return [items[0]]
    indices = sorted({round(index * (len(items) - 1) / (limit - 1)) for index in range(limit)})
    return [items[index] for index in indices]


def safe_filename(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in value)


if __name__ == "__main__":
    raise SystemExit(main())
