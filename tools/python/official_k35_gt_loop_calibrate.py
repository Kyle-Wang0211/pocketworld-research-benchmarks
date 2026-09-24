#!/usr/bin/env python3
"""GT calibration for DA3-BASE K35 official-style streaming with loop closure."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

RESEARCH_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = RESEARCH_ROOT / "tools/python"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import official_k35_loop_sim3_evaluate as loop_eval  # noqa: E402
import tartanground_gt_benchmark as tartan  # noqa: E402
import tum_rgbd_gt_benchmark as tum  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True, choices=["tum", "tartanground"])
    parser.add_argument("--name", required=True)
    parser.add_argument("--sequential-capture-dir", type=Path, required=True)
    parser.add_argument("--sequential-da3-dir", type=Path, required=True)
    parser.add_argument("--vpr-backend-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    centers_against_gt_fn = centers_against_gt_for_dataset(args.dataset)
    started = time.perf_counter()
    seq_plan = loop_eval.read_json(args.sequential_capture_dir / "da3_k_windows.json")
    seq_report = loop_eval.read_json(args.sequential_da3_dir / "mac_da3_window_reports.json")
    retrieval_report = loop_eval.read_json(args.vpr_backend_dir / "loop_retrieval_report.json")
    loop_capture_dir = args.vpr_backend_dir / "loop_capture"
    loop_da3_dir = args.vpr_backend_dir / "loop_da3"
    loop_plan = loop_eval.read_json(loop_capture_dir / "da3_k_windows.json")
    loop_windows = list(loop_plan.get("windows", []))
    if loop_windows:
        loop_report = loop_eval.read_json(loop_da3_dir / "mac_da3_window_reports.json")
    else:
        loop_report = {"windows": []}

    seq_report_by_window = {
        str(window["windowID"]): window for window in seq_report.get("windows", [])
    }
    loop_report_by_window = {
        str(window["windowID"]): window for window in loop_report.get("windows", [])
    }

    sequential_transforms, adjacent_edges = loop_eval.estimate_sequential_transforms(
        seq_plan=seq_plan,
        seq_report_by_window=seq_report_by_window,
        da3_dir=args.sequential_da3_dir,
    )
    loop_constraints, loop_edges = loop_eval.estimate_loop_constraints(
        loop_plan=loop_plan,
        loop_report_by_window=loop_report_by_window,
        seq_report_by_window=seq_report_by_window,
        seq_da3_dir=args.sequential_da3_dir,
        loop_da3_dir=loop_da3_dir,
    )
    optimizer = run_official_optimizer(sequential_transforms, loop_constraints)
    optimized_transforms = optimizer.pop("optimized_transforms", [])

    plan_windows = list(seq_plan.get("windows", []))
    window_ids = [str(window.get("id")) for window in plan_windows]
    centers_by_window = {
        window_id: tum.load_window_centers(seq_report_by_window[window_id], args.sequential_da3_dir)
        for window_id in window_ids
        if window_id in seq_report_by_window
    }

    dense_score = tum.score_official_window_transforms(
        capture_dir=args.sequential_capture_dir,
        plan_windows=plan_windows,
        window_ids=window_ids,
        centers_by_window=centers_by_window,
        transforms=sequential_transforms,
        centers_against_gt_fn=centers_against_gt_fn,
    )
    if optimizer["status"] == "completed" and optimized_transforms:
        loop_score = tum.score_official_window_transforms(
            capture_dir=args.sequential_capture_dir,
            plan_windows=plan_windows,
            window_ids=window_ids,
            centers_by_window=centers_by_window,
            transforms=optimized_transforms,
            centers_against_gt_fn=centers_against_gt_fn,
        )
    else:
        loop_score = {
            "status": optimizer["status"],
            "frame_count": dense_score["frame_count"],
            "pose_rmse": math.nan,
            "pose_p90": math.nan,
            "pose_sim3_scale": math.nan,
        }

    report = {
        "schema_version": "pocketworld_official_da3_base_k35_gt_loop_calibration_v1",
        "dataset": args.dataset,
        "name": args.name,
        "route": (
            "DA3-BASE K35@476x742 official-style sequential chunks -> "
            "SelaVPR++ loop retrieval -> official loop chunk forward -> dense Sim3 -> "
            "official Sim3LoopOptimizer -> GT metric calibration"
        ),
        "capture": {
            "frame_count": count_manifest_frames(args.sequential_capture_dir),
            "sequential_window_count": len(plan_windows),
            "loop_window_count": len(loop_windows),
            "chunk_size": seq_plan.get("windowSize"),
            "overlap": (seq_plan.get("windowingPolicy") or {}).get("overlap"),
            "step": (seq_plan.get("windowingPolicy") or {}).get("step"),
        },
        "retrieval": {
            "backend": retrieval_report.get("backend"),
            "raw_loop_pair_count": retrieval_report.get("raw_loop_pair_count"),
            "loop_result_count": retrieval_report.get("loop_result_count"),
            "threshold_sweep": retrieval_report.get("threshold_sweep"),
            "parameters": retrieval_report.get("parameters"),
        },
        "dense_sim3": {
            "adjacent": loop_eval.summarize_edges(adjacent_edges),
            "gt": score_brief(dense_score),
        },
        "loop_optimizer": {
            "constraints": loop_eval.summarize_edges(loop_edges),
            "optimizer": optimizer,
            "gt": score_brief(loop_score),
            "delta_rmse_m": safe_delta(loop_score.get("pose_rmse"), dense_score.get("pose_rmse")),
            "delta_p90_m": safe_delta(loop_score.get("pose_p90"), dense_score.get("pose_p90")),
        },
        "runtime": {
            "elapsed_s": round(time.perf_counter() - started, 3),
        },
        "dense_score_full": dense_score,
        "loop_score_full": loop_score,
        "adjacent_edges": adjacent_edges,
        "loop_edges": loop_edges,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.name}_official_da3_k35_gt_loop_calibration.json"
    csv_path = args.out_dir / f"{args.name}_official_da3_k35_gt_loop_calibration.csv"
    md_path = args.out_dir / f"{args.name}_official_da3_k35_gt_loop_calibration_zh.md"
    write_json(json_path, report)
    write_csv(csv_path, report)
    write_markdown(md_path, report)
    print(json.dumps(compact_console(report), ensure_ascii=False, indent=2))
    return 0


def centers_against_gt_for_dataset(
    dataset: str,
) -> Callable[[Path, dict[str, np.ndarray]], tuple[np.ndarray, np.ndarray, list[str]]]:
    if dataset == "tum":
        return tum.centers_against_gt
    if dataset == "tartanground":
        return tartan.centers_against_gt
    raise ValueError(dataset)


def run_official_optimizer(
    sequential_transforms: list[tuple[float, np.ndarray, np.ndarray]],
    loop_constraints: list[tuple[int, int, tuple[float, np.ndarray, np.ndarray]]],
) -> dict[str, Any]:
    if not loop_constraints:
        return {"status": "not_run_no_loop_constraints", "optimized_transforms": []}
    from loop_utils.sim3loop import Sim3LoopOptimizer

    config = {
        "Loop": {
            "SIM3_Optimizer": {
                "lang_version": "python",
                "max_iterations": 30,
                "lambda_init": "1e-6",
            }
        }
    }
    started = time.perf_counter()
    try:
        optimizer = Sim3LoopOptimizer(config)
        optimized = optimizer.optimize(sequential_transforms, loop_constraints)
    except Exception as exc:
        return {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": round(time.perf_counter() - started, 3),
            "optimized_transforms": [],
        }
    return {
        "status": "completed",
        "sequential_transform_count": len(sequential_transforms),
        "optimized_transform_count": len(optimized),
        "loop_constraint_count": len(loop_constraints),
        "pre_scale_mean": loop_eval.safe_mean([row[0] for row in sequential_transforms]),
        "post_scale_mean": loop_eval.safe_mean([row[0] for row in optimized]),
        "pre_scale_std": loop_eval.safe_std([row[0] for row in sequential_transforms]),
        "post_scale_std": loop_eval.safe_std([row[0] for row in optimized]),
        "elapsed_s": round(time.perf_counter() - started, 3),
        "optimized_transforms": optimized,
    }


def count_manifest_frames(capture_dir: Path) -> int:
    for name in ("photo_bundle.json", "da3_input_manifest.json"):
        path = capture_dir / name
        if not path.exists():
            continue
        data = loop_eval.read_json(path)
        frames = data.get("frames") or data.get("inputFrames") or []
        if frames:
            return len(frames)
    return 0


def score_brief(score: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": score.get("status", "completed"),
        "frame_count": score.get("frame_count"),
        "pose_rmse_m": as_float(score.get("pose_rmse")),
        "pose_p90_m": as_float(score.get("pose_p90")),
        "pose_p95_m": as_float(score.get("pose_p95")),
        "pose_max_m": as_float(score.get("pose_max")),
        "pose_sim3_scale": as_float(score.get("pose_sim3_scale")),
    }


def compact_console(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "dataset": report["dataset"],
        "name": report["name"],
        "frames": report["capture"]["frame_count"],
        "sequential_windows": report["capture"]["sequential_window_count"],
        "loop_windows": report["capture"]["loop_window_count"],
        "loop_constraints": report["loop_optimizer"]["optimizer"].get("loop_constraint_count"),
        "dense_gt": report["dense_sim3"]["gt"],
        "loop_gt": report["loop_optimizer"]["gt"],
        "delta_rmse_m": report["loop_optimizer"]["delta_rmse_m"],
        "delta_p90_m": report["loop_optimizer"]["delta_p90_m"],
    }


def safe_delta(value: Any, baseline: Any) -> float:
    value_f = as_float(value)
    baseline_f = as_float(baseline)
    if not np.isfinite(value_f) or not np.isfinite(baseline_f):
        return math.nan
    return float(value_f - baseline_f)


def as_float(value: Any) -> float:
    if value is None:
        return math.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def write_csv(path: Path, report: dict[str, Any]) -> None:
    rows = [
        {
            "route": "dense_sim3_only",
            **report["dense_sim3"]["gt"],
            "loop_constraints": 0,
        },
        {
            "route": "dense_sim3_plus_official_loop_optimizer",
            **report["loop_optimizer"]["gt"],
            "loop_constraints": report["loop_optimizer"]["optimizer"].get("loop_constraint_count"),
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    dense = report["dense_sim3"]["gt"]
    loop = report["loop_optimizer"]["gt"]
    retrieval = report["retrieval"]
    optimizer = report["loop_optimizer"]["optimizer"]
    lines = [
        "# 官方 DA3-BASE K35 Streaming GT 定标报告",
        "",
        f"- 数据集：{report['dataset']} / {report['name']}",
        f"- 路线：{report['route']}",
        f"- 帧数：{report['capture']['frame_count']}",
        f"- sequential windows：{report['capture']['sequential_window_count']}",
        f"- loop windows：{report['capture']['loop_window_count']}",
        f"- VPR backend：{retrieval.get('backend')}",
        f"- loop candidates：raw={retrieval.get('raw_loop_pair_count')} / nms={retrieval.get('loop_result_count')}",
        f"- optimizer：{optimizer.get('status')}，constraints={optimizer.get('loop_constraint_count')}",
        "",
        "| 路线 | GT RMSE(m) ↓ | GT P90(m) ↓ | GT P95(m) ↓ | Sim3 scale |",
        "|---|---:|---:|---:|---:|",
        (
            f"| dense Sim3 only | {fmt(dense.get('pose_rmse_m'))} | {fmt(dense.get('pose_p90_m'))} | "
            f"{fmt(dense.get('pose_p95_m'))} | {fmt(dense.get('pose_sim3_scale'))} |"
        ),
        (
            f"| dense Sim3 + official loop optimizer | {fmt(loop.get('pose_rmse_m'))} | "
            f"{fmt(loop.get('pose_p90_m'))} | {fmt(loop.get('pose_p95_m'))} | "
            f"{fmt(loop.get('pose_sim3_scale'))} |"
        ),
        "",
        "## 结论",
        "",
        (
            f"- loop optimizer 相对 dense-only 的 RMSE 变化：{fmt(report['loop_optimizer']['delta_rmse_m'])} m。"
        ),
        (
            f"- loop optimizer 相对 dense-only 的 P90 变化：{fmt(report['loop_optimizer']['delta_p90_m'])} m。"
        ),
        (
            "- 这张表才是外部 GT 米制真值下的最终定标口径；dense Sim3 内部 RMSE 只能说明窗口之间能对齐，"
            "不能单独证明真实世界米制误差。"
        ),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def fmt(value: Any) -> str:
    value_f = as_float(value)
    if not np.isfinite(value_f):
        return "nan"
    return f"{value_f:.4f}"


def json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, tuple):
        return list(value)
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
