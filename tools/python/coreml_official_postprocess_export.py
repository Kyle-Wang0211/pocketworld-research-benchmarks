#!/usr/bin/env python3
"""Apply official DA3 PyTorch postprocess semantics to sealed CoreML window outputs."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from da3_mac_window_export import (  # noqa: E402
    camera_transform_to_opencv_w2c,
    da3_extrinsics,
    da3_intrinsics,
    scale_intrinsics,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--raw-coreml-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--official-src", type=Path, required=True)
    parser.add_argument("--window-id", default="")
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--preserve-window-duplicates",
        action="store_true",
        help=(
            "Research-only: keep duplicate frameIDs from different windows in depth_index.json. "
            "Default production behavior keeps one selected row per frameID."
        ),
    )
    parser.add_argument(
        "--skip-invalid-alignment",
        action="store_true",
        help=(
            "Research-only: skip windows whose official Umeyama pose alignment is degenerate, "
            "instead of failing the entire export."
        ),
    )
    args = parser.parse_args()

    sys.path.insert(0, str(args.official_src))
    from depth_anything_3.utils.pose_align import align_poses_umeyama

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for subdir in ("relative_depth", "confidence", "pred_pose"):
        (args.out_dir / subdir).mkdir(parents=True, exist_ok=True)

    capture = load_capture_context(args.capture_dir)
    raw_reports = read_json(args.raw_coreml_dir / "mac_da3_window_reports.json")
    raw_windows = list(raw_reports.get("windows") or [])
    if args.window_id:
        raw_windows = [row for row in raw_windows if str(row.get("windowID")) == args.window_id]
    if not raw_windows:
        raise ValueError("No windows selected")

    out_windows = []
    window_postprocess = []
    selected_by_frame: dict[str, dict[str, Any]] = {}
    selected_frames_ordered: list[dict[str, Any]] = []

    for window in raw_windows:
        window_id = str(window["windowID"])
        frames = sorted(window.get("frames") or [], key=lambda row: int(row.get("windowSlot", 0)))
        if not frames:
            continue
        window_plan = capture["windows_by_id"].get(window_id, {})
        real_frame_count = int(window_plan.get("realFrameCount") or len(frames))
        align_frame_count = max(1, min(real_frame_count, len(frames)))
        align_slice = slice(0, align_frame_count)
        raw = load_raw_window(args.raw_coreml_dir, frames)
        input_extrinsics, input_intrinsics = build_input_camera_stacks(capture, frames)

        # Official DA3 API order:
        #   align_poses_umeyama(prediction.extrinsics, input_extrinsics, ransac=len>=10)
        #   prediction.intrinsics = input_intrinsics
        #   prediction.extrinsics = input_extrinsics[..., :3, :]
        #   prediction.depth = prediction.depth / pose_scale
        try:
            rot, trans, pose_scale, aligned_extrinsics = align_poses_umeyama(
                raw["extrinsics"][align_slice],
                input_extrinsics[align_slice],
                ransac=align_frame_count >= 10,
                return_aligned=True,
                random_state=args.random_state,
            )
        except Exception as exc:
            if not args.skip_invalid_alignment:
                raise
            out_windows.append(
                {
                    **window,
                    "status": "skipped_invalid_alignment",
                    "frames": [],
                    "telemetry": {
                        **dict(window.get("telemetry") or {}),
                        "officialPostprocess": False,
                        "alignFrameCount": align_frame_count,
                        "paddingFrameCount": max(0, len(frames) - align_frame_count),
                        "skipReason": f"{type(exc).__name__}: {exc}",
                    },
                }
            )
            window_postprocess.append(
                {
                    "windowID": window_id,
                    "status": "skipped_invalid_alignment",
                    "frameCount": len(frames),
                    "alignFrameCount": align_frame_count,
                    "paddingFrameCount": max(0, len(frames) - align_frame_count),
                    "ransac": align_frame_count >= 10,
                    "randomState": args.random_state,
                    "skipReason": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        pose_scale = float(pose_scale)
        if not np.isfinite(pose_scale) or abs(pose_scale) <= 1e-12:
            raise ValueError(f"{window_id} got invalid pose_scale={pose_scale}")

        post_depth = raw["depth"] / pose_scale
        post_conf = raw["conf"]
        post_extrinsics = input_extrinsics[:, :3, :].astype(np.float32, copy=False)
        post_intrinsics = input_intrinsics.astype(np.float32, copy=False)

        out_frames = []
        downstream_ids = official_downstream_ids(window_plan)
        withheld_ids = set(str(value) for value in window_plan.get("withheldForNextOverlapFrameIDs", []))
        for slot, frame in enumerate(frames):
            frame_out = dict(frame)
            write_f32(args.out_dir / str(frame_out["relativeDepthPath"]), post_depth[slot])
            write_f32(args.out_dir / str(frame_out["confidencePath"]), post_conf[slot])
            write_f32(args.out_dir / str(frame_out["predExtrinsicsPath"]), post_extrinsics[slot])
            write_f32(args.out_dir / str(frame_out["predIntrinsicsPath"]), post_intrinsics[slot])
            conf_stats = finite_stats(post_conf[slot])
            depth_stats = finite_stats(post_depth[slot])
            frame_out.update(
                {
                    "status": "completed",
                    "confMedian": conf_stats["median"],
                    "confMean": conf_stats["mean"],
                    "confMin": conf_stats["min"],
                    "confMax": conf_stats["max"],
                    "officialPostprocess": {
                        "source": "Depth-Anything-3 DepthAnything3.inference postprocess",
                        "poseScale": pose_scale,
                        "depthMean": depth_stats["mean"],
                        "rawDepthMean": finite_stats(raw["depth"][slot])["mean"],
                        "alignFrameCount": align_frame_count,
                        "paddingFrameCount": max(0, len(frames) - align_frame_count),
                    },
                    "officialDownstreamFrame": str(frame_out["frameID"]) in downstream_ids,
                    "officialWithheldForNextOverlap": str(frame_out["frameID"]) in withheld_ids,
                }
            )
            out_frames.append(frame_out)
            if args.preserve_window_duplicates:
                if is_preserved_downstream_slot(frame_out, window_plan):
                    selected_frames_ordered.append(dict(frame_out))
            else:
                merge_selected(selected_by_frame, frame_out, window_plan)

        out_window = {
            **window,
            "officialSaveFrameIDs": window_plan.get("officialSaveFrameIDs", []),
            "downstreamFrameIDs": window_plan.get("downstreamFrameIDs", []),
            "officialSaveLocalIndices": window_plan.get("officialSaveLocalIndices", []),
            "withheldForNextOverlapFrameIDs": window_plan.get("withheldForNextOverlapFrameIDs", []),
            "status": "completed",
            "frames": out_frames,
            "telemetry": {
                **dict(window.get("telemetry") or {}),
                "officialPostprocess": True,
                "poseScale": pose_scale,
                "randomState": args.random_state,
                "alignFrameCount": align_frame_count,
                "paddingFrameCount": max(0, len(frames) - align_frame_count),
            },
        }
        out_windows.append(out_window)
        window_postprocess.append(
            {
                "windowID": window_id,
                "status": "completed",
                "frameCount": len(frames),
                "alignFrameCount": align_frame_count,
                "paddingFrameCount": max(0, len(frames) - align_frame_count),
                "ransac": align_frame_count >= 10,
                "randomState": args.random_state,
                "poseScale": pose_scale,
                "rotation": np.asarray(rot, dtype=float).tolist(),
                "translation": np.asarray(trans, dtype=float).reshape(-1).tolist(),
                "rawDepth": summarize_array(raw["depth"][align_slice].reshape(-1)),
                "postDepth": summarize_array(post_depth[align_slice].reshape(-1)),
                "rawConfidence": summarize_array(raw["conf"][align_slice].reshape(-1)),
                "rawPredPoseVsInput": pose_stack_metrics(
                    raw["extrinsics"][align_slice],
                    input_extrinsics[align_slice, :3, :],
                ),
                "alignedInputVsRawPredPose": pose_stack_metrics(
                    np.asarray(aligned_extrinsics, dtype=np.float32)[:, :3, :],
                    raw["extrinsics"][align_slice],
                ),
                "postPoseVsInput": pose_stack_metrics(
                    post_extrinsics[align_slice],
                    input_extrinsics[align_slice, :3, :],
                ),
                "rawPredIntrinsicsVsInput": matrix_metrics(
                    raw["intrinsics"][align_slice],
                    input_intrinsics[align_slice],
                ),
            }
        )

    if args.preserve_window_duplicates:
        selected_frames = selected_frames_ordered
    else:
        selected_frames = sorted(selected_by_frame.values(), key=lambda row: int(row.get("frameIndex", 0)))
    write_json(args.out_dir / "mac_da3_window_reports.json", {"windows": out_windows})
    write_depth_index_like_raw(
        raw_coreml_dir=args.raw_coreml_dir,
        out_dir=args.out_dir,
        frames=selected_frames,
        windows=out_windows,
        postprocess=window_postprocess,
    )
    report = {
        "schema_version": "pocketworld_coreml_official_postprocess_export_v1",
        "inputs": {
            "capture_dir": str(args.capture_dir),
            "raw_coreml_dir": str(args.raw_coreml_dir),
            "official_src": str(args.official_src),
        },
        "outputs": {
            "out_dir": str(args.out_dir),
            "depth_index": str(args.out_dir / "depth_index.json"),
            "runner_report": str(args.out_dir / "depth_runner_report.json"),
        },
            "official_postprocess": {
                "algorithm": [
                "align_poses_umeyama(raw_pred_extrinsics, input_extrinsics)",
                "depth = raw_depth / pose_scale",
                "intrinsics = input_intrinsics",
                "extrinsics = input_extrinsics[:3,:]",
            ],
            "note": "This does not modify CoreML inference; it changes only the postprocess/export semantics to match the official PyTorch API.",
        },
            "windows": window_postprocess,
            "preserve_window_duplicates": args.preserve_window_duplicates,
        }
    write_json(args.out_dir / "official_postprocess_report.json", report)
    write_markdown(args.out_dir / "official_postprocess_report_zh.md", report)
    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))
    return 0


def load_capture_context(capture_dir: Path) -> dict[str, Any]:
    bundle = read_json(capture_dir / "photo_bundle.json")
    input_manifest = maybe_read_json(capture_dir / "da3_input_manifest.json")
    k_windows = maybe_read_json(capture_dir / "da3_k_windows.json")
    return {
        "capture_dir": capture_dir,
        "frames_by_id": {str(row["id"]): row for row in bundle.get("frames", [])},
        "input_by_id": {str(row["id"]): row for row in input_manifest.get("frames", [])},
        "windows_by_id": {
            str(row.get("id")): row for row in k_windows.get("windows", [])
        },
    }


def build_input_camera_stacks(
    capture: dict[str, Any],
    frames: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    extrinsics = []
    intrinsics = []
    for frame in frames:
        frame_id = str(frame["frameID"])
        capture_frame = capture["frames_by_id"][frame_id]
        input_frame = capture["input_by_id"].get(frame_id, {})
        height = int(frame["depthHeight"])
        width = int(frame["depthWidth"])
        extrinsics.append(da3_extrinsics(capture_frame, input_frame))
        intrinsics.append(da3_intrinsics(capture_frame, input_frame, height, width))
    return np.stack(extrinsics, axis=0), np.stack(intrinsics, axis=0)


def load_raw_window(coreml_dir: Path, frames: list[dict[str, Any]]) -> dict[str, np.ndarray]:
    depth, conf, extrinsics, intrinsics = [], [], [], []
    for frame in frames:
        height = int(frame["depthHeight"])
        width = int(frame["depthWidth"])
        depth.append(
            np.fromfile(coreml_dir / str(frame["relativeDepthPath"]), dtype="<f4").reshape(height, width)
        )
        conf.append(
            np.fromfile(coreml_dir / str(frame["confidencePath"]), dtype="<f4").reshape(height, width)
        )
        extrinsics.append(
            np.fromfile(coreml_dir / str(frame["predExtrinsicsPath"]), dtype="<f4").reshape(3, 4)
        )
        intrinsics.append(
            np.fromfile(coreml_dir / str(frame["predIntrinsicsPath"]), dtype="<f4").reshape(3, 3)
        )
    return {
        "depth": np.stack(depth, axis=0).astype(np.float32, copy=False),
        "conf": np.stack(conf, axis=0).astype(np.float32, copy=False),
        "extrinsics": np.stack(extrinsics, axis=0).astype(np.float32, copy=False),
        "intrinsics": np.stack(intrinsics, axis=0).astype(np.float32, copy=False),
    }


def merge_selected(
    selected_by_frame: dict[str, dict[str, Any]],
    row: dict[str, Any],
    window: dict[str, Any],
) -> None:
    frame_id = str(row["frameID"])
    downstream_ids = official_downstream_ids(window)
    if downstream_ids and frame_id not in downstream_ids:
        return
    current = selected_by_frame.get(frame_id)
    if current is None or (row.get("officialDownstreamFrame") and not current.get("officialDownstreamFrame")):
            selected_by_frame[frame_id] = dict(row)


def is_preserved_downstream_slot(row: dict[str, Any], window: dict[str, Any]) -> bool:
    slot = int(row.get("windowSlot", -1))
    save_indices = {
        int(value)
        for value in window.get("officialSaveLocalIndices", [])
        if value is not None
    }
    if save_indices:
        return slot in save_indices
    real_count = int(window.get("realFrameCount") or 0)
    if real_count > 0:
        return 0 <= slot < real_count
    frame_id = str(row["frameID"])
    downstream_ids = official_downstream_ids(window)
    return not downstream_ids or frame_id in downstream_ids


def official_downstream_ids(window: dict[str, Any]) -> set[str]:
    for key in ("downstreamFrameIDs", "officialSaveFrameIDs"):
        values = set(str(value) for value in window.get(key, []))
        if values:
            return values
    return set(str(value) for value in window.get("coreFrameIDs", []))


def write_depth_index_like_raw(
    *,
    raw_coreml_dir: Path,
    out_dir: Path,
    frames: list[dict[str, Any]],
    windows: list[dict[str, Any]],
    postprocess: list[dict[str, Any]],
) -> None:
    raw_depth_index = maybe_read_json(raw_coreml_dir / "depth_index.json")
    depth_index = dict(raw_depth_index)
    depth_index.update(
        {
            "schema_version": raw_depth_index.get("schema_version", "aether_depth_index_v1"),
            "status": "completed",
            "official_postprocess": {
                "schema_version": "pocketworld_coreml_official_postprocess_export_v1",
                "source_raw_dir": str(raw_coreml_dir),
                "algorithm": "official DA3 Umeyama pose_scale + input intrinsics/extrinsics refill",
                "windows": postprocess,
            },
            "frame_count": len(frames),
            "completed_count": len(frames),
            "pending_count": 0,
            "failed_count": 0,
            "frames": frames,
        }
    )
    write_json(out_dir / "depth_index.json", depth_index)
    raw_runner = maybe_read_json(raw_coreml_dir / "depth_runner_report.json")
    runner = dict(raw_runner)
    runner.update(
        {
            "schema_version": raw_runner.get("schema_version", "aether_da3_depth_runner_report_v1"),
            "status": "completed",
            "rule": "Official DA3 postprocess applied to sealed CoreML raw window outputs.",
            "window_count": len(windows),
            "frame_count": len(frames),
            "completed_count": len(frames),
            "official_postprocess": postprocess,
            "windows": windows,
        }
    )
    write_json(out_dir / "depth_runner_report.json", runner)
    raw_log = raw_coreml_dir / "mac_da3_window_export_log.jsonl"
    if raw_log.exists():
        shutil.copyfile(raw_log, out_dir / "mac_da3_window_export_log.jsonl")


def pose_stack_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    centers_left = np.stack([camera_center_from_w2c(row) for row in left], axis=0)
    centers_right = np.stack([camera_center_from_w2c(row) for row in right], axis=0)
    center_dist = np.linalg.norm(centers_left - centers_right, axis=1)
    rot_angles = np.asarray(
        [rotation_angle_deg(left[i, :3, :3], right[i, :3, :3]) for i in range(left.shape[0])],
        dtype=np.float64,
    )
    return {
        "camera_center_distance": summarize_array(center_dist),
        "rotation_angle_deg": summarize_array(rot_angles),
    }


def matrix_metrics(left: np.ndarray, right: np.ndarray) -> dict[str, Any]:
    diff = np.asarray(left, dtype=np.float64) - np.asarray(right, dtype=np.float64)
    return {
        "mae": float(np.mean(np.abs(diff))),
        "rmse": float(np.sqrt(np.mean(diff * diff))),
        "max_abs": float(np.max(np.abs(diff))),
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


def finite_stats(value: np.ndarray) -> dict[str, float]:
    arr = np.asarray(value, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {"median": math.nan, "mean": math.nan, "min": math.nan, "max": math.nan}
    return {
        "median": float(np.median(finite)),
        "mean": float(np.mean(finite)),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
    }


def write_f32(path: Path, value: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.asarray(value, dtype="<f4").tofile(path)


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def maybe_read_json(path: Path) -> dict[str, Any]:
    return read_json(path) if path.exists() else {}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# CoreML Official DA3 Postprocess Export",
        "",
        "## 做了什么",
        "",
        "- 不重新跑 CoreML inference。",
        "- 读取 sealed CoreML raw window 输出。",
        "- 按官方 PyTorch API 后处理顺序执行：`align_poses_umeyama(raw_pred_extrinsics, input_extrinsics)`。",
        "- 用 `depth = raw_depth / pose_scale` 写回 depth。",
        "- 用输入相机的 intrinsics/extrinsics 回填官方 postprocess 语义。",
        "",
        "## Window Summary",
        "",
        "| window | status | frames | ransac | pose_scale | raw depth mean | post depth mean | raw pose center median | post pose center median | raw K MAE |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["windows"]:
        if row.get("status") == "skipped_invalid_alignment":
            lines.append(
                "| {window} | skipped_invalid_alignment | {frames} | {ransac} | n/a | n/a | n/a | n/a | n/a | n/a |".format(
                    window=row["windowID"],
                    frames=row["frameCount"],
                    ransac=str(row["ransac"]),
                )
            )
            continue
        lines.append(
            "| {window} | completed | {frames} | {ransac} | {scale:.8g} | {raw:.6g} | {post:.6g} | {raw_pose:.6g} | {post_pose:.6g} | {k_mae:.6g} |".format(
                window=row["windowID"],
                frames=row["frameCount"],
                ransac=str(row["ransac"]),
                scale=float(row["poseScale"]),
                raw=float(row["rawDepth"].get("mean", math.nan)),
                post=float(row["postDepth"].get("mean", math.nan)),
                raw_pose=float(
                    row["rawPredPoseVsInput"]["camera_center_distance"].get("median", math.nan)
                ),
                post_pose=float(row["postPoseVsInput"]["camera_center_distance"].get("median", math.nan)),
                k_mae=float(row["rawPredIntrinsicsVsInput"].get("mae", math.nan)),
            )
        )
    lines.extend(
        [
            "",
            "## 判断",
            "",
            "这份输出用于验证官方 postprocess 是否能解释 CoreML/PyTorch 小 K parity 中的 scale、pose 和 intrinsics 差异。它不包含 bbox 裁剪或自研融合。",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": report["schema_version"],
        "out_dir": report["outputs"]["out_dir"],
        "windows": [
            {
                "windowID": row["windowID"],
                "status": row.get("status", "completed"),
                "poseScale": row.get("poseScale"),
                "rawDepthMean": (row.get("rawDepth") or {}).get("mean"),
                "postDepthMean": (row.get("postDepth") or {}).get("mean"),
                "rawPoseCenterMedian": (
                    (row.get("rawPredPoseVsInput") or {}).get("camera_center_distance") or {}
                ).get("median"),
                "postPoseCenterMedian": (
                    (row.get("postPoseVsInput") or {}).get("camera_center_distance") or {}
                ).get("median"),
            }
            for row in report["windows"]
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
