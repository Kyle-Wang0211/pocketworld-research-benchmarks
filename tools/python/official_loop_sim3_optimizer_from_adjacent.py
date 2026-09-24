#!/usr/bin/env python3
"""Run official-style loop Sim3 optimization from verified adjacent Sim3 edges.

This script keeps the DA3-Streaming structure:

1. Adjacent transforms are read from the official adjacent dense Sim3 diagnostic.
2. Loop constraints are estimated from official loop chunks:
   original chunk range <- loop chunk range A/B, then compute A -> B Sim3.
3. The official Sim3LoopOptimizer optimizes the sequential transform chain.

It does not alter point clouds, clean points, mesh, or invent new fusion logic.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
RESEARCH_ROOT = SCRIPT_DIR.parents[1]
OFFICIAL_DA3_STREAMING = RESEARCH_ROOT / "tools/vendor/official_da3_streaming"
for path in (SCRIPT_DIR, OFFICIAL_DA3_STREAMING):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from official_k35_adjacent_dense_sim3_diagnostics import (  # noqa: E402
    estimate_dense_sim3_rows,
    read_json,
    transform_to_tuple,
    write_json,
)
from official_k35_loop_sim3_evaluate import (  # noqa: E402
    compute_sim3_ab,
    safe_mean,
    safe_std,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sequential-capture-dir", type=Path, required=True)
    parser.add_argument("--sequential-da3-dir", type=Path, required=True)
    parser.add_argument("--adjacent-sim3-json", type=Path, required=True)
    parser.add_argument("--vpr-backend-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--confidence-mode",
        choices=["streaming_subtract_one", "raw"],
        default="streaming_subtract_one",
    )
    args = parser.parse_args()

    started = time.perf_counter()
    seq_plan = read_json(args.sequential_capture_dir / "da3_k_windows.json")
    seq_report = read_json(args.sequential_da3_dir / "mac_da3_window_reports.json")
    adjacent_report = read_json(args.adjacent_sim3_json)
    retrieval_report = read_json(args.vpr_backend_dir / "loop_retrieval_report.json")
    loop_capture_dir = args.vpr_backend_dir / "loop_capture"
    loop_da3_dir = args.vpr_backend_dir / "loop_da3"
    loop_plan = read_json(loop_capture_dir / "da3_k_windows.json")
    loop_report = read_json(loop_da3_dir / "mac_da3_window_reports.json")

    seq_report_by_window = {
        str(window["windowID"]): window for window in seq_report.get("windows", [])
    }
    loop_report_by_window = {
        str(window["windowID"]): window for window in loop_report.get("windows", [])
    }

    sequential_transforms, adjacent_edges = sequential_transforms_from_report(
        seq_plan,
        adjacent_report,
    )
    loop_constraints, loop_edges = estimate_loop_constraints(
        loop_plan=loop_plan,
        loop_report_by_window=loop_report_by_window,
        seq_report_by_window=seq_report_by_window,
        seq_da3_dir=args.sequential_da3_dir,
        loop_da3_dir=loop_da3_dir,
        confidence_mode=args.confidence_mode,
    )
    optimizer_report = run_optimizer_detailed(sequential_transforms, loop_constraints)
    report = {
        "schema_version": "pocketworld_official_loop_sim3_optimizer_from_adjacent_v1",
        "route": (
            "K35 official-save sequential CoreML -> verified official adjacent dense Sim3 "
            "-> SelaVPR++ loop chunks -> official loop dense Sim3 -> Sim3LoopOptimizer"
        ),
        "inputs": {
            "sequential_capture_dir": str(args.sequential_capture_dir),
            "sequential_da3_dir": str(args.sequential_da3_dir),
            "adjacent_sim3_json": str(args.adjacent_sim3_json),
            "vpr_backend_dir": str(args.vpr_backend_dir),
            "confidence_mode": args.confidence_mode,
        },
        "license_notes": {
            "da3_streaming_code": "Apache-2.0 headers in local DA3-Streaming sources",
            "selavprpp": "MIT license in local tools/vendor/vpr/SelaVPRplusplus/LICENSE",
            "caution": "This is not legal advice; mobile production still needs dependency/weights license audit.",
        },
        "retrieval": {
            "backend": retrieval_report.get("backend"),
            "parameters": retrieval_report.get("parameters"),
            "raw_loop_pair_count": retrieval_report.get("raw_loop_pair_count"),
            "loop_result_count": retrieval_report.get("loop_result_count"),
            "threshold_sweep": retrieval_report.get("threshold_sweep"),
        },
        "sequential_window_count": len(seq_plan.get("windows", [])),
        "loop_window_count": len(loop_plan.get("windows", [])),
        "adjacent": summarize_adjacent(adjacent_edges),
        "loop": summarize_loop_edges(loop_edges),
        "optimizer": optimizer_report,
        "adjacent_edges": adjacent_edges,
        "loop_edges": loop_edges,
        "elapsed_s": round(time.perf_counter() - started, 3),
    }
    write_json(args.out, report)
    write_markdown(args.out.with_suffix(".md"), report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def sequential_transforms_from_report(
    seq_plan: dict[str, Any],
    adjacent_report: dict[str, Any],
) -> tuple[list[tuple[float, np.ndarray, np.ndarray]], list[dict[str, Any]]]:
    windows = list(seq_plan.get("windows") or [])
    edges = [edge for edge in adjacent_report.get("edges", []) if edge.get("status") == "estimated"]
    if len(edges) != max(0, len(windows) - 1):
        raise ValueError(
            f"Expected {len(windows) - 1} adjacent edges, got {len(edges)}"
        )
    transforms = []
    checked_edges = []
    for index, edge in enumerate(edges):
        parent_id = str(windows[index]["id"])
        current_id = str(windows[index + 1]["id"])
        if str(edge.get("parentWindowID")) != parent_id or str(edge.get("currentWindowID")) != current_id:
            raise ValueError(
                "Adjacent JSON order does not match capture windows: "
                f"{edge.get('parentWindowID')}->{edge.get('currentWindowID')} vs "
                f"{parent_id}->{current_id}"
            )
        transform = {
            "scale": float(edge["sim3_scale"]),
            "rotation": np.asarray(edge["sim3_rotation"], dtype=np.float64),
            "translation": np.asarray(edge["sim3_translation"], dtype=np.float64),
        }
        transforms.append(transform_to_tuple(transform))
        checked_edges.append(
            {
                "edgeType": "adjacent",
                "parentWindowID": parent_id,
                "currentWindowID": current_id,
                "overlapFrameCount": edge.get("overlapFrameCount"),
                "point_count": edge.get("point_count"),
                "rmse": edge.get("rmse"),
                "p90": edge.get("p90"),
                "sim3_scale": edge.get("sim3_scale"),
                "sim3_rotation_angle_deg": edge.get("sim3_rotation_angle_deg"),
                "sim3_translation_norm": edge.get("sim3_translation_norm"),
            }
        )
    return transforms, checked_edges


def estimate_loop_constraints(
    *,
    loop_plan: dict[str, Any],
    loop_report_by_window: dict[str, dict[str, Any]],
    seq_report_by_window: dict[str, dict[str, Any]],
    seq_da3_dir: Path,
    loop_da3_dir: Path,
    confidence_mode: str,
) -> tuple[list[tuple[int, int, tuple[float, np.ndarray, np.ndarray]]], list[dict[str, Any]]]:
    constraints = []
    edges = []
    for loop_window in loop_plan.get("windows", []):
        window_id = str(loop_window.get("id"))
        if window_id not in loop_report_by_window:
            edges.append({"edgeType": "loop", "loopWindowID": window_id, "status": "missing_loop_da3"})
            continue
        chunk = loop_window.get("loopChunk") or {}
        chunk_a = int(chunk["chunkIndexA"])
        chunk_b = int(chunk["chunkIndexB"])
        range_a = [int(v) for v in chunk["rangeA"]]
        range_b = [int(v) for v in chunk["rangeB"]]
        slot_a = [int(v) for v in chunk["slotRangeA"]]
        slot_b = [int(v) for v in chunk["slotRangeB"]]

        original_a_rows = rows_by_global_index(
            seq_report_by_window[f"window_{chunk_a:03d}"],
            range_a[0],
            range_a[1],
        )
        original_b_rows = rows_by_global_index(
            seq_report_by_window[f"window_{chunk_b:03d}"],
            range_b[0],
            range_b[1],
        )
        loop_rows = sorted(
            loop_report_by_window[window_id].get("frames", []),
            key=lambda row: int(row.get("windowSlot", 0)),
        )
        loop_a_rows = loop_rows[slot_a[0] : slot_a[1]]
        loop_b_rows = loop_rows[slot_b[0] : slot_b[1]]
        if (
            len(original_a_rows) != len(loop_a_rows)
            or len(original_b_rows) != len(loop_b_rows)
            or not original_a_rows
            or not original_b_rows
        ):
            edges.append(
                {
                    "edgeType": "loop",
                    "loopWindowID": window_id,
                    "chunkIndexA": chunk_a,
                    "chunkIndexB": chunk_b,
                    "status": "skipped_range_mismatch",
                    "originalACount": len(original_a_rows),
                    "loopACount": len(loop_a_rows),
                    "originalBCount": len(original_b_rows),
                    "loopBCount": len(loop_b_rows),
                }
            )
            continue

        transform_a, edge_a = estimate_dense_sim3_rows(
            target_rows=original_a_rows,
            source_rows=loop_a_rows,
            target_da3_dir=seq_da3_dir,
            source_da3_dir=loop_da3_dir,
            confidence_mode=confidence_mode,
        )
        transform_b, edge_b = estimate_dense_sim3_rows(
            target_rows=original_b_rows,
            source_rows=loop_b_rows,
            target_da3_dir=seq_da3_dir,
            source_da3_dir=loop_da3_dir,
            confidence_mode=confidence_mode,
        )
        loop_ab = compute_sim3_ab(transform_to_tuple(transform_a), transform_to_tuple(transform_b))
        constraints.append((chunk_a, chunk_b, loop_ab))
        edges.append(
            {
                "edgeType": "loop",
                "loopWindowID": window_id,
                "chunkIndexA": chunk_a,
                "chunkIndexB": chunk_b,
                "rangeA": range_a,
                "rangeB": range_b,
                "status": "estimated",
                "a_point_count": edge_a.get("point_count"),
                "b_point_count": edge_b.get("point_count"),
                "a_rmse": edge_a.get("rmse"),
                "b_rmse": edge_b.get("rmse"),
                "a_p90": edge_a.get("p90"),
                "b_p90": edge_b.get("p90"),
                "sim3_scale": float(loop_ab[0]),
                "sim3_rotation_angle_deg": rotation_angle_degrees(np.asarray(loop_ab[1])),
                "sim3_translation_norm": float(np.linalg.norm(loop_ab[2])),
            }
        )
    return constraints, edges


def run_optimizer_detailed(
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
        "pre_scale_mean": safe_mean([row[0] for row in sequential_transforms]),
        "post_scale_mean": safe_mean([row[0] for row in optimized]),
        "pre_scale_std": safe_std([row[0] for row in sequential_transforms]),
        "post_scale_std": safe_std([row[0] for row in optimized]),
        "elapsed_s": round(time.perf_counter() - started, 3),
        "optimized_transforms": [
            {
                "edgeIndex": index,
                "sim3_scale": float(transform[0]),
                "sim3_rotation": np.asarray(transform[1], dtype=np.float64).tolist(),
                "sim3_translation": np.asarray(transform[2], dtype=np.float64).reshape(3).tolist(),
                "sim3_rotation_angle_deg": rotation_angle_degrees(np.asarray(transform[1], dtype=np.float64)),
                "sim3_translation_norm": float(np.linalg.norm(transform[2])),
            }
            for index, transform in enumerate(optimized)
        ],
    }


def rows_by_global_index(window_report: dict[str, Any], start: int, end: int) -> list[dict[str, Any]]:
    rows = sorted(window_report.get("frames", []), key=lambda row: int(row.get("frameIndex", 0)))
    return [row for row in rows if start <= int(row.get("frameIndex", -1)) < end]


def rotation_angle_degrees(rotation: np.ndarray) -> float:
    value = (float(np.trace(rotation)) - 1.0) * 0.5
    value = max(-1.0, min(1.0, value))
    return float(np.degrees(np.arccos(value)))


def summarize_adjacent(edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "edge_count": len(edges),
        "estimated_count": sum(1 for edge in edges if edge.get("sim3_scale") is not None),
        "rmse_mean": safe_mean([edge.get("rmse") for edge in edges]),
        "p90_mean": safe_mean([edge.get("p90") for edge in edges]),
        "scale_mean": safe_mean([edge.get("sim3_scale") for edge in edges]),
        "scale_std": safe_std([edge.get("sim3_scale") for edge in edges]),
        "scale_min": safe_min([edge.get("sim3_scale") for edge in edges]),
        "scale_max": safe_max([edge.get("sim3_scale") for edge in edges]),
        "rotation_angle_deg_max": safe_max([edge.get("sim3_rotation_angle_deg") for edge in edges]),
        "translation_norm_max": safe_max([edge.get("sim3_translation_norm") for edge in edges]),
    }


def summarize_loop_edges(edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "edge_count": len(edges),
        "estimated_count": sum(1 for edge in edges if edge.get("status") == "estimated"),
        "scale_mean": safe_mean([edge.get("sim3_scale") for edge in edges]),
        "scale_std": safe_std([edge.get("sim3_scale") for edge in edges]),
        "scale_min": safe_min([edge.get("sim3_scale") for edge in edges]),
        "scale_max": safe_max([edge.get("sim3_scale") for edge in edges]),
        "rotation_angle_deg_max": safe_max([edge.get("sim3_rotation_angle_deg") for edge in edges]),
        "translation_norm_max": safe_max([edge.get("sim3_translation_norm") for edge in edges]),
        "a_rmse_mean": safe_mean([edge.get("a_rmse") for edge in edges]),
        "b_rmse_mean": safe_mean([edge.get("b_rmse") for edge in edges]),
        "a_p90_mean": safe_mean([edge.get("a_p90") for edge in edges]),
        "b_p90_mean": safe_mean([edge.get("b_p90") for edge in edges]),
    }


def safe_values(values: list[Any]) -> np.ndarray:
    return np.asarray(
        [float(value) for value in values if value is not None and np.isfinite(float(value))],
        dtype=np.float64,
    )


def safe_min(values: list[Any]) -> float:
    arr = safe_values(values)
    return float(np.min(arr)) if arr.size else math.nan


def safe_max(values: list[Any]) -> float:
    arr = safe_values(values)
    return float(np.max(arr)) if arr.size else math.nan


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    adj = report["adjacent"]
    loop = report["loop"]
    opt = report["optimizer"]
    lines = [
        "# Official Loop Sim3 Optimizer From Adjacent",
        "",
        "## 做了什么",
        "",
        "- 使用已验证的 adjacent dense Sim3 JSON 作为 sequential transforms。",
        "- 使用 SelaVPR++ loop capture 的官方 loop chunk 规则估计 loop constraints。",
        "- 调用官方 Sim3LoopOptimizer。",
        "- 不导出点云、不做清理、不做 mesh。",
        "",
        "## Retrieval",
        "",
        f"- backend: {report['retrieval']['backend']}",
        f"- raw_loop_pair_count: {report['retrieval']['raw_loop_pair_count']}",
        f"- loop_result_count: {report['retrieval']['loop_result_count']}",
        f"- parameters: `{report['retrieval']['parameters']}`",
        "",
        "## Adjacent",
        "",
        f"- edge_count: {adj['edge_count']}",
        f"- scale_range: {adj['scale_min']:.8g} .. {adj['scale_max']:.8g}",
        f"- rmse_mean: {adj['rmse_mean']:.8g}",
        f"- p90_mean: {adj['p90_mean']:.8g}",
        f"- rotation_angle_deg_max: {adj['rotation_angle_deg_max']:.8g}",
        "",
        "## Loop",
        "",
        f"- edge_count: {loop['edge_count']}",
        f"- estimated_count: {loop['estimated_count']}",
        f"- scale_range: {loop['scale_min']:.8g} .. {loop['scale_max']:.8g}",
        f"- a_rmse_mean: {loop['a_rmse_mean']:.8g}",
        f"- b_rmse_mean: {loop['b_rmse_mean']:.8g}",
        f"- rotation_angle_deg_max: {loop['rotation_angle_deg_max']:.8g}",
        "",
        "## Optimizer",
        "",
        f"- status: {opt.get('status')}",
        f"- loop_constraint_count: {opt.get('loop_constraint_count')}",
        f"- pre_scale_mean/std: {opt.get('pre_scale_mean')} / {opt.get('pre_scale_std')}",
        f"- post_scale_mean/std: {opt.get('post_scale_mean')} / {opt.get('post_scale_std')}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    optimizer = dict(report["optimizer"])
    optimizer.pop("optimized_transforms", None)
    return {
        "schema_version": report["schema_version"],
        "confidence_mode": report["inputs"]["confidence_mode"],
        "sequential_window_count": report["sequential_window_count"],
        "loop_window_count": report["loop_window_count"],
        "retrieval_loop_result_count": report["retrieval"]["loop_result_count"],
        "adjacent": report["adjacent"],
        "loop": report["loop"],
        "optimizer": optimizer,
        "out": report["inputs"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
