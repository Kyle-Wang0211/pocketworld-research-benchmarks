#!/usr/bin/env python3
"""Audit small-K CoreML vs official PyTorch DA3 outputs."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np
from PIL import Image

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


DEFAULT_CASES = ["k03_res742_mps", "k05_res742_mps", "k10_res476_mps"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coreml-dir", type=Path, required=True)
    parser.add_argument("--pytorch-sweep-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--window-id", default="window_000")
    parser.add_argument("--cases", nargs="+", default=DEFAULT_CASES)
    parser.add_argument("--sample-limit", type=int, default=500_000)
    parser.add_argument("--seed", type=int, default=5210)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    frames = load_coreml_frames(args.coreml_dir, args.window_id)

    case_reports = []
    for case_name in args.cases:
        case_dir = args.pytorch_sweep_dir / case_name
        if not case_dir.exists():
            case_reports.append({"case": case_name, "status": "missing", "path": str(case_dir)})
            continue
        case_reports.append(
            audit_case(
                case_name=case_name,
                case_dir=case_dir,
                frames=frames,
                coreml_dir=args.coreml_dir,
                out_dir=args.out_dir,
                sample_limit=args.sample_limit,
                seed=args.seed,
            )
        )

    report = {
        "schema_version": "pocketworld_coreml_pytorch_small_k_parity_audit_v1",
        "inputs": {
            "coreml_dir": str(args.coreml_dir),
            "pytorch_sweep_dir": str(args.pytorch_sweep_dir),
            "window_id": args.window_id,
        },
        "scope": {
            "coreml_context": "fixed N35 sealed CoreML window, using the first K slots",
            "pytorch_context": "official PyTorch variable-K forward for each saved K",
            "hard_parity_cases": "same output HxW only, currently K=3/5 at process_res=742",
            "weak_cases": "shape mismatch cases use resized CoreML only as a diagnostic",
            "pose_note": "Saved PyTorch sweep extrinsics/intrinsics are official postprocessed values, not raw model logits.",
        },
        "parameters": {
            "cases": args.cases,
            "sample_limit": args.sample_limit,
            "seed": args.seed,
        },
        "cases": case_reports,
        "interpretation": interpret_report(case_reports),
    }
    write_json(args.out_dir / "coreml_pytorch_small_k_parity_report.json", report)
    write_markdown(args.out_dir / "coreml_pytorch_small_k_parity_report_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def load_coreml_frames(coreml_dir: Path, window_id: str) -> list[dict[str, Any]]:
    reports = read_json(coreml_dir / "mac_da3_window_reports.json")
    windows = {str(row["windowID"]): row for row in reports.get("windows", [])}
    if window_id not in windows:
        raise KeyError(f"{window_id} not found in {coreml_dir / 'mac_da3_window_reports.json'}")
    return sorted(windows[window_id].get("frames", []), key=lambda row: int(row.get("windowSlot", 0)))


def audit_case(
    *,
    case_name: str,
    case_dir: Path,
    frames: list[dict[str, Any]],
    coreml_dir: Path,
    out_dir: Path,
    sample_limit: int,
    seed: int,
) -> dict[str, Any]:
    parsed = parse_case_name(case_name)
    pytorch = load_pytorch_case(case_dir)
    k = int(pytorch["depth"].shape[0])
    if k > len(frames):
        raise ValueError(f"{case_name} needs {k} CoreML frames, only {len(frames)} available")
    coreml = load_coreml_stack(frames[:k], coreml_dir)
    direct_shape_match = tuple(coreml["depth"].shape) == tuple(pytorch["depth"].shape)

    comparison_coreml = coreml
    comparison_mode = "direct_pixel" if direct_shape_match else "resized_coreml_weak"
    if not direct_shape_match:
        target_hw = tuple(pytorch["depth"].shape[1:])
        comparison_coreml = {
            **coreml,
            "depth": resize_stack(coreml["depth"], target_hw),
            "conf": resize_stack(coreml["conf"], target_hw),
        }

    case_seed = seed + stable_case_offset(case_name)
    depth_metrics = array_pair_metrics(
        comparison_coreml["depth"],
        pytorch["depth"],
        sample_limit=sample_limit,
        seed=case_seed,
    )
    conf_metrics = array_pair_metrics(
        comparison_coreml["conf"],
        pytorch["conf"],
        sample_limit=sample_limit,
        seed=case_seed + 1,
    )
    intrinsics_metrics = matrix_metrics(coreml["intrinsics"], pytorch["intrinsics"], kind="intrinsics")
    pose_metrics_report = pose_metrics(coreml["extrinsics"], pytorch["extrinsics"])

    png_path = out_dir / f"{case_name}_parity_views.png"
    write_case_figure(
        png_path,
        case_name=case_name,
        coreml=comparison_coreml,
        pytorch=pytorch,
        depth_scale=float(depth_metrics.get("scale_only", {}).get("scale", 1.0)),
        comparison_mode=comparison_mode,
    )

    return {
        "case": case_name,
        "status": "compared",
        "parsed": parsed,
        "k": k,
        "coreml_shape": list(coreml["depth"].shape),
        "pytorch_shape": list(pytorch["depth"].shape),
        "comparison_shape": list(comparison_coreml["depth"].shape),
        "comparison_mode": comparison_mode,
        "direct_shape_match": direct_shape_match,
        "limitation": (
            "CoreML is fixed N35 context; PyTorch is variable-K context. "
            "This is an audit signal, not a strict proof of same-context equivalence."
        ),
        "outputs": {
            "parity_views_png": str(png_path),
        },
        "frames": [
            {
                "slot": int(row.get("windowSlot", index)),
                "frame_id": str(row.get("frameID")),
                "image": str(row.get("imageRelativePath")),
            }
            for index, row in enumerate(frames[:k])
        ],
        "depth": depth_metrics,
        "confidence": conf_metrics,
        "intrinsics": intrinsics_metrics,
        "pose": pose_metrics_report,
        "summaries": {
            "coreml_depth": summarize_array(coreml["depth"].reshape(-1)),
            "pytorch_depth": summarize_array(pytorch["depth"].reshape(-1)),
            "coreml_conf": summarize_array(coreml["conf"].reshape(-1)),
            "pytorch_conf": summarize_array(pytorch["conf"].reshape(-1)),
        },
    }


def parse_case_name(case_name: str) -> dict[str, Any]:
    match = re.match(r"k(?P<k>\d+)_res(?P<res>\d+)_(?P<device>.+)", case_name)
    if not match:
        return {}
    return {
        "k": int(match.group("k")),
        "process_res": int(match.group("res")),
        "device": match.group("device"),
    }


def stable_case_offset(case_name: str) -> int:
    return sum((index + 1) * ord(ch) for index, ch in enumerate(case_name))


def load_pytorch_case(case_dir: Path) -> dict[str, np.ndarray]:
    return {
        "depth": np.load(case_dir / "pytorch_depth.npy").astype(np.float32, copy=False),
        "conf": np.load(case_dir / "pytorch_conf.npy").astype(np.float32, copy=False),
        "intrinsics": np.load(case_dir / "pytorch_intrinsics.npy").astype(np.float32, copy=False),
        "extrinsics": np.load(case_dir / "pytorch_extrinsics.npy").astype(np.float32, copy=False),
        "processed_images": np.load(case_dir / "pytorch_processed_images.npy"),
    }


def load_coreml_stack(frames: list[dict[str, Any]], coreml_dir: Path) -> dict[str, np.ndarray]:
    depths, confs, intrinsics, extrinsics = [], [], [], []
    for frame in frames:
        height = int(frame["depthHeight"])
        width = int(frame["depthWidth"])
        depths.append(
            np.fromfile(coreml_dir / str(frame["relativeDepthPath"]), dtype="<f4")
            .reshape(height, width)
            .astype(np.float32, copy=False)
        )
        confs.append(
            np.fromfile(coreml_dir / str(frame["confidencePath"]), dtype="<f4")
            .reshape(height, width)
            .astype(np.float32, copy=False)
        )
        intrinsics.append(
            np.fromfile(coreml_dir / str(frame["predIntrinsicsPath"]), dtype="<f4")
            .reshape(3, 3)
            .astype(np.float32, copy=False)
        )
        extrinsics.append(
            np.fromfile(coreml_dir / str(frame["predExtrinsicsPath"]), dtype="<f4")
            .reshape(3, 4)
            .astype(np.float32, copy=False)
        )
    return {
        "depth": np.stack(depths, axis=0),
        "conf": np.stack(confs, axis=0),
        "intrinsics": np.stack(intrinsics, axis=0),
        "extrinsics": np.stack(extrinsics, axis=0),
    }


def resize_stack(values: np.ndarray, target_hw: tuple[int, int]) -> np.ndarray:
    target_h, target_w = target_hw
    out = []
    for frame in values:
        image = Image.fromarray(frame.astype(np.float32), mode="F")
        resized = image.resize((target_w, target_h), Image.Resampling.BILINEAR)
        out.append(np.asarray(resized, dtype=np.float32))
    return np.stack(out, axis=0)


def array_pair_metrics(
    left: np.ndarray,
    right: np.ndarray,
    *,
    sample_limit: int,
    seed: int,
) -> dict[str, Any]:
    left_flat = np.asarray(left, dtype=np.float64).reshape(-1)
    right_flat = np.asarray(right, dtype=np.float64).reshape(-1)
    valid = np.isfinite(left_flat) & np.isfinite(right_flat)
    left_valid = left_flat[valid]
    right_valid = right_flat[valid]
    total_valid = int(left_valid.size)
    if total_valid == 0:
        return {"status": "no_valid_pairs"}

    if total_valid > sample_limit:
        rng = np.random.default_rng(seed)
        idx = rng.choice(total_valid, size=sample_limit, replace=False)
        left_cmp = left_valid[idx]
        right_cmp = right_valid[idx]
        sampled = True
    else:
        left_cmp = left_valid
        right_cmp = right_valid
        sampled = False

    raw = residual_metrics(left_cmp, right_cmp)
    scale = fit_scale(left_cmp, right_cmp)
    scale_metrics = {"scale": scale, **residual_metrics(left_cmp * scale, right_cmp)}
    affine_a, affine_b = fit_affine(left_cmp, right_cmp)
    affine_metrics = {
        "scale": affine_a,
        "offset": affine_b,
        **residual_metrics(left_cmp * affine_a + affine_b, right_cmp),
    }

    return {
        "status": "ok",
        "valid_pair_count": total_valid,
        "sampled": sampled,
        "sample_count": int(left_cmp.size),
        "left_summary": summarize_array(left_valid),
        "right_summary": summarize_array(right_valid),
        "raw": raw,
        "scale_only": scale_metrics,
        "affine": affine_metrics,
        "mean_ratio_right_over_left": safe_div(float(np.mean(right_cmp)), float(np.mean(left_cmp))),
        "pearson": pearson(left_cmp, right_cmp),
    }


def residual_metrics(pred: np.ndarray, target: np.ndarray) -> dict[str, float]:
    diff = pred - target
    abs_diff = np.abs(diff)
    denom = np.maximum(np.abs(target), 1e-6)
    rel = abs_diff / denom
    return {
        "mean_signed": float(np.mean(diff)),
        "mae": float(np.mean(abs_diff)),
        "rmse": float(np.sqrt(np.mean(diff * diff))),
        "median_abs": float(np.median(abs_diff)),
        "p90_abs": float(np.percentile(abs_diff, 90)),
        "p99_abs": float(np.percentile(abs_diff, 99)),
        "max_abs": float(np.max(abs_diff)),
        "median_relative": float(np.median(rel)),
        "p90_relative": float(np.percentile(rel, 90)),
    }


def fit_scale(left: np.ndarray, right: np.ndarray) -> float:
    denom = float(np.dot(left, left))
    if denom <= 1e-12:
        return math.nan
    return float(np.dot(left, right) / denom)


def fit_affine(left: np.ndarray, right: np.ndarray) -> tuple[float, float]:
    design = np.stack([left, np.ones_like(left)], axis=1)
    try:
        coeff, *_ = np.linalg.lstsq(design, right, rcond=None)
    except np.linalg.LinAlgError:
        return math.nan, math.nan
    return float(coeff[0]), float(coeff[1])


def pearson(left: np.ndarray, right: np.ndarray) -> float:
    left_c = left - np.mean(left)
    right_c = right - np.mean(right)
    denom = float(np.linalg.norm(left_c) * np.linalg.norm(right_c))
    if denom <= 1e-12:
        return math.nan
    return float(np.dot(left_c, right_c) / denom)


def matrix_metrics(coreml: np.ndarray, pytorch: np.ndarray, *, kind: str) -> dict[str, Any]:
    if coreml.shape != pytorch.shape:
        return {
            "status": "shape_mismatch",
            "coreml_shape": list(coreml.shape),
            "pytorch_shape": list(pytorch.shape),
        }
    diff = coreml.astype(np.float64) - pytorch.astype(np.float64)
    result: dict[str, Any] = {
        "status": "ok",
        "shape": list(coreml.shape),
        "mae": float(np.mean(np.abs(diff))),
        "rmse": float(np.sqrt(np.mean(diff * diff))),
        "max_abs": float(np.max(np.abs(diff))),
    }
    if kind == "intrinsics":
        result["fx"] = component_metrics(coreml[:, 0, 0], pytorch[:, 0, 0])
        result["fy"] = component_metrics(coreml[:, 1, 1], pytorch[:, 1, 1])
        result["cx"] = component_metrics(coreml[:, 0, 2], pytorch[:, 0, 2])
        result["cy"] = component_metrics(coreml[:, 1, 2], pytorch[:, 1, 2])
    return result


def component_metrics(coreml: np.ndarray, pytorch: np.ndarray) -> dict[str, Any]:
    diff = coreml.astype(np.float64) - pytorch.astype(np.float64)
    return {
        "coreml": summarize_array(coreml),
        "pytorch": summarize_array(pytorch),
        "mean_abs_diff": float(np.mean(np.abs(diff))),
        "max_abs_diff": float(np.max(np.abs(diff))),
        "mean_signed_diff": float(np.mean(diff)),
    }


def pose_metrics(coreml: np.ndarray, pytorch: np.ndarray) -> dict[str, Any]:
    if coreml.shape != pytorch.shape:
        return {
            "status": "shape_mismatch",
            "coreml_shape": list(coreml.shape),
            "pytorch_shape": list(pytorch.shape),
        }
    centers_coreml = np.stack([camera_center_from_w2c(ext) for ext in coreml], axis=0)
    centers_pytorch = np.stack([camera_center_from_w2c(ext) for ext in pytorch], axis=0)
    center_diff = centers_coreml - centers_pytorch
    center_dist = np.linalg.norm(center_diff, axis=1)
    angles = np.asarray(
        [rotation_angle_deg(coreml[i, :3, :3], pytorch[i, :3, :3]) for i in range(coreml.shape[0])],
        dtype=np.float64,
    )
    return {
        "status": "ok",
        "note": "PyTorch extrinsics here are official postprocessed/input-aligned values saved by the sweep.",
        "camera_center_distance": summarize_array(center_dist),
        "rotation_angle_deg": summarize_array(angles),
        "coreml_centers": centers_coreml.tolist(),
        "pytorch_centers": centers_pytorch.tolist(),
    }


def camera_center_from_w2c(extrinsics: np.ndarray) -> np.ndarray:
    rotation = extrinsics[:3, :3].astype(np.float64)
    translation = extrinsics[:3, 3].astype(np.float64)
    return (-rotation.T @ translation).astype(np.float64)


def rotation_angle_deg(left_r: np.ndarray, right_r: np.ndarray) -> float:
    rel = left_r.astype(np.float64) @ right_r.astype(np.float64).T
    value = (float(np.trace(rel)) - 1.0) * 0.5
    value = max(-1.0, min(1.0, value))
    return float(np.degrees(np.arccos(value)))


def summarize_array(values: np.ndarray) -> dict[str, float | int]:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {"count": 0}
    return {
        "count": int(finite.size),
        "min": float(np.min(finite)),
        "p05": float(np.percentile(finite, 5)),
        "median": float(np.median(finite)),
        "mean": float(np.mean(finite)),
        "p95": float(np.percentile(finite, 95)),
        "max": float(np.max(finite)),
        "std": float(np.std(finite)),
    }


def safe_div(num: float, den: float) -> float:
    if abs(den) <= 1e-12:
        return math.nan
    return float(num / den)


def write_case_figure(
    path: Path,
    *,
    case_name: str,
    coreml: dict[str, np.ndarray],
    pytorch: dict[str, np.ndarray],
    depth_scale: float,
    comparison_mode: str,
) -> None:
    k = min(int(coreml["depth"].shape[0]), 5)
    fig, axes = plt.subplots(k, 5, figsize=(15, max(3, 2.8 * k)), squeeze=False)
    scaled_core_depth = coreml["depth"] * depth_scale
    depth_abs = np.abs(scaled_core_depth - pytorch["depth"])
    conf_abs = np.abs(coreml["conf"] - pytorch["conf"])
    for row in range(k):
        draw_image(axes[row, 0], coreml["depth"][row], f"slot {row} CoreML depth")
        draw_image(axes[row, 1], pytorch["depth"][row], f"slot {row} PyTorch depth")
        draw_image(axes[row, 2], depth_abs[row], f"scaled depth abs")
        draw_image(axes[row, 3], coreml["conf"][row], f"CoreML conf")
        draw_image(axes[row, 4], conf_abs[row], f"conf abs")
    fig.suptitle(f"{case_name} parity audit ({comparison_mode})", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def draw_image(axis: Any, values: np.ndarray, title: str) -> None:
    finite = values[np.isfinite(values)]
    if finite.size:
        lo = float(np.percentile(finite, 2))
        hi = float(np.percentile(finite, 98))
        if hi <= lo:
            hi = lo + 1.0
    else:
        lo, hi = 0.0, 1.0
    axis.imshow(values, cmap="viridis", vmin=lo, vmax=hi)
    axis.set_title(title, fontsize=8)
    axis.axis("off")


def interpret_report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    compared = [case for case in cases if case.get("status") == "compared"]
    hard = [case for case in compared if case.get("direct_shape_match")]
    weak = [case for case in compared if not case.get("direct_shape_match")]
    largest_depth_rel = None
    largest_conf_mae = None
    for case in hard:
        depth_rel = case.get("depth", {}).get("scale_only", {}).get("median_relative")
        conf_mae = case.get("confidence", {}).get("raw", {}).get("mae")
        if depth_rel is not None:
            largest_depth_rel = max(largest_depth_rel or 0.0, float(depth_rel))
        if conf_mae is not None:
            largest_conf_mae = max(largest_conf_mae or 0.0, float(conf_mae))
    return {
        "hard_case_count": len(hard),
        "weak_case_count": len(weak),
        "largest_hard_depth_scale_aligned_median_relative": largest_depth_rel,
        "largest_hard_conf_raw_mae": largest_conf_mae,
        "summary": (
            "主信号看 K=3/5@742。depth 结构高度相关，但需要明显全局 scale 才贴近 PyTorch；"
            "confidence 差异偏大；pose/intrinsics 当前比较的是 CoreML raw-ish 输出和 PyTorch "
            "official postprocess 后的值。下一步应优先把 CoreML 输出补齐官方 Umeyama / pose_scale / "
            "intrinsics-extrinsics 回填，而不是继续调 bbox。K=10@476 shape 不一致，只能作为弱参考。"
        ),
    }


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "case_count": len(report["cases"]),
        "interpretation": report["interpretation"],
        "cases": [
            {
                "case": case.get("case"),
                "status": case.get("status"),
                "mode": case.get("comparison_mode"),
                "direct": case.get("direct_shape_match"),
                "depth_scale": case.get("depth", {}).get("scale_only", {}).get("scale"),
                "depth_scaled_median_rel": case.get("depth", {})
                .get("scale_only", {})
                .get("median_relative"),
                "conf_mae": case.get("confidence", {}).get("raw", {}).get("mae"),
            }
            for case in report["cases"]
        ],
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# CoreML / Official PyTorch Small-K Parity Audit",
        "",
        "## 范围",
        "",
        "- CoreML：固定 N35 sealed model 的 `window_000`，取前 K 个 slot。",
        "- PyTorch：官方 DA3 PyTorch variable-K forward 的小 K 输出。",
        "- 硬对比：只有输出 HxW 完全一致的 case，当前主要是 `K=3/5 @ process_res=742`。",
        "- 弱对比：shape 不一致时，把 CoreML resize 到 PyTorch shape，只作为诊断，不作为 parity 判定。",
        "- 注意：当前 PyTorch sweep 保存的是官方 postprocess 后的 intrinsics/extrinsics，不是 raw model pose logits。",
        "",
        "## Case Summary",
        "",
        "| case | mode | direct | depth scale | depth scaled median rel | conf raw MAE | pose center median | png |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for case in report["cases"]:
        if case.get("status") != "compared":
            lines.append(f"| {case.get('case')} | {case.get('status')} | - | - | - | - | - | - |")
            continue
        depth_scale = case.get("depth", {}).get("scale_only", {}).get("scale")
        depth_rel = case.get("depth", {}).get("scale_only", {}).get("median_relative")
        conf_mae = case.get("confidence", {}).get("raw", {}).get("mae")
        pose_med = case.get("pose", {}).get("camera_center_distance", {}).get("median")
        png = case.get("outputs", {}).get("parity_views_png", "-")
        lines.append(
            "| {case} | {mode} | {direct} | {scale} | {rel} | {conf} | {pose} | `{png}` |".format(
                case=case.get("case"),
                mode=case.get("comparison_mode"),
                direct=str(case.get("direct_shape_match")),
                scale=format_float(depth_scale),
                rel=format_float(depth_rel),
                conf=format_float(conf_mae),
                pose=format_float(pose_med),
                png=png,
            )
        )
    lines.extend(
        [
            "",
            "## 读法",
            "",
            "- `depth scale` 是把 CoreML depth 乘到最接近 PyTorch depth 的全局比例；如果比例远离 1，说明两边 depth 尺度不在同一坐标系。",
            "- `depth scaled median rel` 是全局 scale 对齐后的中位相对误差，越小越接近。",
            "- `conf raw MAE` 是 confidence 原值平均绝对差；confidence 不做 scale 后的主判定。",
            "- `pose center median` 是 CoreML pose 与 PyTorch postprocessed/input-aligned pose 的相机中心距离中位数。",
            "",
            "## 初步结论",
            "",
            report.get("interpretation", {}).get("summary", ""),
            "",
            "这份 audit 先定位软件对齐问题，不尝试通过 bbox 或自研过滤修图。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def format_float(value: Any) -> str:
    if value is None:
        return "-"
    try:
        if not np.isfinite(float(value)):
            return "-"
        return f"{float(value):.6g}"
    except Exception:
        return "-"


if __name__ == "__main__":
    raise SystemExit(main())
