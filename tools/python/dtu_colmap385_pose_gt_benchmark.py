#!/usr/bin/env python3
"""Run COLMAP-385 DA3 windows on DTU64 camera-pose GT.

This is a research-only benchmark. It prepares DTU64 scans as PocketWorld-like
captures, lets the COLMAP view-graph executor choose the slots385 window plan,
runs the sealed DA3-BASE K35@476x742 CoreML model, and evaluates predicted
camera centers against DTU camera GT after Sim3 alignment.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


RESEARCH_ROOT = Path(__file__).resolve().parents[2]
AETHER_ROOT = RESEARCH_ROOT.parent
DTU64_ROOT = AETHER_ROOT / "workspace/benchmark_dataset/dtu64"
COLMAP_EXECUTOR = RESEARCH_ROOT / "tools/python/colmap_view_graph_executor.py"
DA3_EXPORTER = RESEARCH_ROOT / "tools/python/da3_mac_window_export.py"
DEFAULT_MODEL = AETHER_ROOT / "pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage"


@dataclass(frozen=True)
class CameraRecord:
    index: int
    image_path: Path
    extrinsic_w2c: np.ndarray
    intrinsic: np.ndarray
    center: np.ndarray


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtu64-root", type=Path, default=DTU64_ROOT)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--scans", nargs="+", default=["scan105"])
    parser.add_argument("--slot-target", type=int, default=385)
    parser.add_argument("--bridge-overlap", type=int, default=6)
    parser.add_argument("--colmap-bin", default="colmap")
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--compute-unit", default="all", choices=["cpu", "cpu_and_gpu", "cpu_and_ne", "all"])
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--skip-da3", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    results = []
    for scan in args.scans:
        scan_started = time.perf_counter()
        scan_out = args.out_dir / scan
        capture_dir = scan_out / "capture_dtu64"
        colmap_out = scan_out / "colmap_view_graph_slots385"
        da3_out = scan_out / "mac_da3_slots385"
        prepare_dtu_capture(args.dtu64_root, scan, capture_dir, force=not args.reuse)
        run_colmap_plan(args, capture_dir, colmap_out)
        overlay_dir = colmap_out / "capture_overlay_slots385"
        if not overlay_dir.exists():
            # The generic executor names by actual slots. Keep this strict so
            # a future window-size change cannot silently evaluate the wrong plan.
            raise FileNotFoundError(overlay_dir)
        if not args.skip_da3:
            run_da3(args, overlay_dir, da3_out)
        metrics = evaluate_pose_gt(args.dtu64_root, scan, da3_out, colmap_out)
        metrics["elapsed_s"] = round(time.perf_counter() - scan_started, 3)
        write_json(scan_out / "pose_gt_metrics.json", metrics)
        write_scan_summary(scan_out / "summary.md", metrics)
        print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
        results.append(metrics)

    summary = {
        "schema_version": "aether_dtu_colmap385_pose_gt_benchmark_v1",
        "route": "COLMAP-style slots385 -> sealed DA3-BASE K35@476x742 -> DTU64 camera-pose GT",
        "slot_target": args.slot_target,
        "bridge_overlap": args.bridge_overlap,
        "scans": args.scans,
        "elapsed_s": round(time.perf_counter() - started, 3),
        "aggregate": aggregate(results),
        "results": results,
    }
    write_json(args.out_dir / "summary.json", summary)
    write_overall_summary(args.out_dir / "summary.md", summary)
    print(json.dumps(summary["aggregate"], ensure_ascii=False, indent=2), flush=True)
    return 0


def prepare_dtu_capture(dtu_root: Path, scan: str, capture_dir: Path, *, force: bool) -> None:
    if capture_dir.exists() and force:
        shutil.rmtree(capture_dir)
    if (capture_dir / "photo_bundle.json").exists():
        return
    photos_depth = capture_dir / "photos_depth"
    photos_highres = capture_dir / "photos_highres"
    previews = capture_dir / "previews"
    for folder in (photos_depth, photos_highres, previews):
        folder.mkdir(parents=True, exist_ok=True)

    records = load_dtu_records(dtu_root, scan)
    centers = np.stack([record.center for record in records], axis=0)
    scene_center = centers.mean(axis=0)
    max_pair_dist = max_pairwise_distance(centers)

    frames = []
    input_frames = []
    nodes = []
    for order, record in enumerate(records):
        frame_id = f"{scan}-{record.index:06d}"
        with Image.open(record.image_path) as image:
            image = image.convert("RGB")
            w, h = image.size
            jpg_name = f"{frame_id}.jpg"
            image.save(photos_depth / jpg_name, quality=95)
            image.save(photos_highres / jpg_name, quality=95)
            preview = image.copy()
            preview.thumbnail((512, 512))
            preview.save(previews / jpg_name, quality=90)

        azimuth, elevation = camera_angles(record.center, scene_center)
        c2w_arkit = opencv_w2c_to_arkit_c2w(record.extrinsic_w2c)
        fx, fy = float(record.intrinsic[0, 0]), float(record.intrinsic[1, 1])
        cx, cy = float(record.intrinsic[0, 2]), float(record.intrinsic[1, 2])
        quality_score = 1.0
        frames.append(
            {
                "id": frame_id,
                "highresFilename": jpg_name,
                "previewFilename": jpg_name,
                "timestamp": float(order),
                "triggerTimestamp": float(order),
                "azimuth": math.radians(azimuth),
                "elevation": math.radians(elevation),
                "captureKind": "dtu64_gt_research_frame",
                "poseSyncQuality": "dtu64_camera_gt",
                "imageWidth": w,
                "imageHeight": h,
                "quality": {
                    "accepted": True,
                    "score": quality_score,
                    "viewGraphWeight": quality_score,
                    "kWindowWeight": quality_score,
                    "textureBestViewWeight": quality_score,
                    "rejectReasons": [],
                },
                "cameraTransform": c2w_arkit.reshape(-1, order="F").astype(float).tolist(),
                "intrinsics": [fx, fy, cx, cy],
                "cameraRadiusM": float(np.linalg.norm(record.center - scene_center)),
                "radiusShellID": "dtu64",
                "poseSource": "dtu64_gt",
                "trackingState": "normal",
                "cellID": f"dtu_{scan}_{order:03d}",
                "dtuIndex": record.index,
            }
        )
        sx = 742.0 / float(w)
        sy = 476.0 / float(h)
        input_frames.append(
            {
                "id": frame_id,
                "sourceHighresRelativePath": f"photos_highres/{jpg_name}",
                "depthImageRelativePath": f"photos_depth/{jpg_name}",
                "sourceWidth": w,
                "sourceHeight": h,
                "inputWidth": 742,
                "inputHeight": 476,
                "resize": {
                    "mode": "direct_stretch",
                    "interpolation": "cubic",
                    "colorSpace": "sRGB",
                    "jpegQuality": 95,
                },
                "transform": {
                    "scaleX": sx,
                    "scaleY": sy,
                    "offsetX": 0.0,
                    "offsetY": 0.0,
                    "cropX": 0.0,
                    "cropY": 0.0,
                    "cropWidth": w,
                    "cropHeight": h,
                },
                "intrinsicsTransform": {
                    "fxScale": sx,
                    "fyScale": sy,
                    "cxScale": sx,
                    "cyScale": sy,
                    "cxOffset": 0.0,
                    "cyOffset": 0.0,
                },
            }
        )
        nodes.append(
            {
                "id": frame_id,
                "timestamp": float(order),
                "cellID": f"dtu_{scan}_{order:03d}",
                "azimuthDeg": azimuth,
                "elevationDeg": elevation,
            }
        )

    edges = build_pose_proxy_edges(frames, centers, max_pair_dist)
    model = {
        "id": "DA3-BASE",
        "license": "Apache-2.0",
        "mobileTag": "da3:base:k35:476x742:active",
        "resourceName": "DA3BASE_476x742_N35_pose",
        "windowSize": 35,
        "inputWidth": 742,
        "inputHeight": 476,
        "inputSizeStatus": "locked_da3_base_k35_476x742_benchmark_2026_05_25",
        "commercialSafe": True,
    }
    write_json(
        capture_dir / "photo_bundle.json",
        {
            "schemaVersion": "aether_photo_bundle_v1",
            "captureVersion": "dtu64_pose_gt_research",
            "sourceKind": "dtu64",
            "photosHighresDir": "photos_highres",
            "previewsDir": "previews",
            "frames": frames,
        },
    )
    write_json(
        capture_dir / "da3_input_manifest.json",
        {
            "schemaVersion": "aether_da3_input_manifest_v1",
            "sourceManifest": "photo_bundle.json",
            "photosDepthDir": "photos_depth",
            "model": model,
            "inputSizeLocked": True,
            "inputWidth": 742,
            "inputHeight": 476,
            "preprocessOwner": "research_dtu64_capture_adapter",
            "frameCount": len(input_frames),
            "frames": input_frames,
        },
    )
    write_json(
        capture_dir / "view_graph.json",
        {
            "schemaVersion": "aether_view_graph_v1",
            "graphKind": "dtu64_pose_proxy_complete_graph",
            "sourceManifest": "photo_bundle.json",
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "maxNeighborsPerNode": len(nodes) - 1,
            "featureMatchStatus": "pending_colmap_executor",
            "nodes": nodes,
            "edges": edges,
            "summary": {"rule": "DTU GT pose proxy used only to propose COLMAP candidate pairs"},
        },
    )
    write_json(
        capture_dir / "model_policy.json",
        {
            "schemaVersion": "aether_model_policy_v1",
            "status": "locked",
            "selectedDepthModel": model,
            "rule": "research DTU64 COLMAP-385 GT benchmark",
        },
    )
    write_json(
        capture_dir / "da3_k_windows.json",
        {
            "schemaVersion": "aether_da3_k_windows_v1",
            "sourceManifest": "photo_bundle.json",
            "sourceViewGraph": "view_graph.json",
            "model": model,
            "windowSize": 35,
            "windowingPolicy": {
                "kind": "dtu64_seed_only_replaced_by_colmap_executor",
                "productionAllowed": False,
            },
            "loopClosurePolicy": {},
            "inputSizeLocked": True,
            "inputHeight": 476,
            "inputWidth": 742,
            "bridgeGraph": [],
            "loopCandidates": [],
            "uncoveredFrameIDs": [],
            "uncoveredFrameCount": 0,
            "windowCount": 1,
            "windows": [
                {
                    "id": "window_seed",
                    "modelTag": model["mobileTag"],
                    "modelResourceName": model["resourceName"],
                    "selectionMode": "seed_only",
                    "frameIDs": [frame["id"] for frame in frames[:35]],
                    "uniqueFrameIDs": [frame["id"] for frame in frames[:35]],
                    "coreFrameIDs": [frame["id"] for frame in frames[:35]],
                    "bridgeFrameIDs": [],
                    "frameCount": 35,
                    "uniqueFrameCount": 35,
                    "coreFrameCount": 35,
                    "bridgeFrameCount": 0,
                    "inputHeight": 476,
                    "inputWidth": 742,
                }
            ],
        },
    )
    write_json(capture_dir / "bundle_validation.json", {"status": "ok", "frameCount": len(frames)})
    write_json(
        capture_dir / "dtu64_gt_manifest.json",
        {
            "scan": scan,
            "cameraConvention": "DTU OpenCV w2c; app adapter stores ARKit c2w only for DA3 executor compatibility",
            "frames": [
                {
                    "frameID": frame["id"],
                    "dtuIndex": frame["dtuIndex"],
                    "cameraPath": str(dtu_root / "Cameras" / f"{frame['dtuIndex']:08d}_cam.txt"),
                    "imagePath": str(dtu_root / scan / "image" / f"{frame['dtuIndex']:06d}.png"),
                }
                for frame in frames
            ],
        },
    )


def load_dtu_records(dtu_root: Path, scan: str) -> list[CameraRecord]:
    image_dir = dtu_root / scan / "image"
    images = sorted(image_dir.glob("*.png"), key=lambda p: int(p.stem))
    records = []
    for image_path in images:
        index = int(image_path.stem)
        ext, intr = parse_cam(dtu_root / "Cameras" / f"{index:08d}_cam.txt")
        center = camera_center_from_w2c(ext)
        records.append(CameraRecord(index=index, image_path=image_path, extrinsic_w2c=ext, intrinsic=intr, center=center))
    if not records:
        raise RuntimeError(f"No DTU images found for {scan}")
    return records


def parse_cam(path: Path) -> tuple[np.ndarray, np.ndarray]:
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    ext_idx = lines.index("extrinsic") + 1
    intr_idx = lines.index("intrinsic") + 1
    ext = np.asarray([[float(v) for v in lines[ext_idx + i].split()] for i in range(4)], dtype=np.float32)
    intr = np.asarray([[float(v) for v in lines[intr_idx + i].split()] for i in range(3)], dtype=np.float32)
    return ext, intr


def camera_center_from_w2c(w2c: np.ndarray) -> np.ndarray:
    r = w2c[:3, :3].astype(np.float64)
    t = w2c[:3, 3].astype(np.float64)
    return (-r.T @ t).astype(np.float64)


def opencv_w2c_to_arkit_c2w(w2c: np.ndarray) -> np.ndarray:
    c2w_opencv = np.linalg.inv(w2c.astype(np.float64))
    cv_from_arkit_camera = np.diag([1.0, -1.0, -1.0, 1.0])
    return (c2w_opencv @ cv_from_arkit_camera).astype(np.float32)


def camera_angles(center: np.ndarray, scene_center: np.ndarray) -> tuple[float, float]:
    v = center.astype(np.float64) - scene_center.astype(np.float64)
    r = max(float(np.linalg.norm(v)), 1e-9)
    az = math.degrees(math.atan2(float(v[0]), float(v[2]))) % 360.0
    el = math.degrees(math.asin(float(np.clip(v[1] / r, -1.0, 1.0))))
    return az, el


def max_pairwise_distance(centers: np.ndarray) -> float:
    max_dist = 0.0
    for i in range(len(centers)):
        d = np.linalg.norm(centers[i + 1 :] - centers[i], axis=1)
        if d.size:
            max_dist = max(max_dist, float(d.max()))
    return max(max_dist, 1e-6)


def build_pose_proxy_edges(frames: list[dict[str, Any]], centers: np.ndarray, max_dist: float) -> list[dict[str, Any]]:
    edges = []
    directions = centers - centers.mean(axis=0, keepdims=True)
    directions /= np.maximum(np.linalg.norm(directions, axis=1, keepdims=True), 1e-9)
    for i in range(len(frames)):
        for j in range(i + 1, len(frames)):
            dot = float(np.clip(np.dot(directions[i], directions[j]), -1.0, 1.0))
            angular_gap = math.degrees(math.acos(dot))
            baseline = float(np.linalg.norm(centers[i] - centers[j]))
            temporal_gap = float(abs(j - i))
            angle_score = max(0.0, 1.0 - angular_gap / 180.0)
            baseline_score = max(0.0, 1.0 - baseline / max_dist)
            temporal_score = max(0.0, 1.0 - temporal_gap / max(len(frames) - 1, 1))
            score = 0.55 * angle_score + 0.25 * baseline_score + 0.20 * temporal_score
            edges.append(
                {
                    "sourceID": frames[i]["id"],
                    "targetID": frames[j]["id"],
                    "score": float(score),
                    "angularGapDeg": float(angular_gap),
                    "baselineM": float(baseline),
                    "radiusRatio": float(baseline / max_dist),
                    "temporalGapSec": temporal_gap,
                    "overlapProxy": float(angle_score),
                    "sameRadiusShell": True,
                    "supportKind": "dtu64_pose_proxy",
                    "reasons": ["gt_camera_angle_proxy", "temporal_neighbor_proxy"],
                }
            )
    return edges


def run_colmap_plan(args: argparse.Namespace, capture_dir: Path, colmap_out: Path) -> None:
    command = [
        args.python_bin,
        str(COLMAP_EXECUTOR),
        "--capture-dir",
        str(capture_dir),
        "--output-dir",
        str(colmap_out),
        "--colmap-bin",
        args.colmap_bin,
        "--slot-targets",
        str(args.slot_target),
        "--bridge-overlap",
        str(args.bridge_overlap),
        "--view-graph-top-k",
        "16",
        "--temporal-neighbors",
        "6",
    ]
    if args.reuse:
        command.append("--reuse")
    run_command(command, colmap_out / "driver_log.jsonl", "colmap_plan")


def run_da3(args: argparse.Namespace, overlay_dir: Path, da3_out: Path) -> None:
    command = [
        args.python_bin,
        str(DA3_EXPORTER),
        "--capture-dir",
        str(overlay_dir),
        "--out-dir",
        str(da3_out),
        "--model",
        str(args.model),
        "--compute-unit",
        args.compute_unit,
        "--resume",
    ]
    run_command(command, da3_out / "driver_log.jsonl", "da3_coreml")


def run_command(command: list[str], log_path: Path, event: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    append_jsonl(log_path, {"event": f"{event}_start", "command": command})
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    append_jsonl(
        log_path,
        {
            "event": f"{event}_done",
            "returncode": proc.returncode,
            "elapsed_s": round(time.perf_counter() - started, 3),
            "tail": proc.stdout[-12000:],
        },
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{event} failed\n{proc.stdout[-6000:]}")


def evaluate_pose_gt(dtu_root: Path, scan: str, da3_out: Path, colmap_out: Path) -> dict[str, Any]:
    depth_index_path = da3_out / "depth_index.json"
    if not depth_index_path.exists():
        raise FileNotFoundError(depth_index_path)
    depth_index = read_json(depth_index_path)
    plan = read_json(colmap_out / "da3_k_windows_colmap_slots385.json")
    report = read_json(colmap_out / "colmap_view_graph_report.json")
    selected_pred_centers = []
    selected_gt_centers = []
    frame_rows = []
    for frame in depth_index.get("frames", []):
        frame_id = str(frame["frameID"])
        dtu_idx = int(frame_id.rsplit("-", 1)[1])
        pred_ext = np.fromfile(da3_out / str(frame["predExtrinsicsPath"]), dtype="<f4").reshape(3, 4)
        pred_w2c = np.eye(4, dtype=np.float64)
        pred_w2c[:3, :4] = pred_ext.astype(np.float64)
        gt_ext, _ = parse_cam(dtu_root / "Cameras" / f"{dtu_idx:08d}_cam.txt")
        pred_center = camera_center_from_w2c(pred_w2c)
        gt_center = camera_center_from_w2c(gt_ext)
        selected_pred_centers.append(pred_center)
        selected_gt_centers.append(gt_center)
        frame_rows.append({"frameID": frame_id, "dtuIndex": dtu_idx, "windowID": frame.get("windowID"), "windowRole": frame.get("windowRole")})
    if not selected_pred_centers:
        raise RuntimeError("No DA3 frame rows for evaluation")

    selected_pred = np.stack(selected_pred_centers, axis=0)
    selected_gt = np.stack(selected_gt_centers, axis=0)
    unstitched_err, unstitched_scale = umeyama_align(selected_pred, selected_gt)
    per_window = evaluate_per_window_pose(dtu_root, scan, da3_out)
    stitched = evaluate_stitched_windows(dtu_root, scan, da3_out, plan)
    metrics = {
        "schema_version": "aether_dtu_colmap385_pose_gt_metrics_v1",
        "scan": scan,
        "metric_kind": "camera_center_pose_gt_after_sim3_with_window_stitch",
        "route": "COLMAP slots385 + DA3-BASE K35@476x742",
        "frame_count": len(frame_rows),
        "window_count": int(plan.get("windowCount", 0)),
        "actual_slots": int(plan.get("windowingPolicy", {}).get("actualSlots", 0)),
        "selected_frame_count": int(plan.get("selectedFrameCount", 0)),
        "dropped_frame_count": int(plan.get("droppedFrameCount", 0)),
        "colmap_verified_pairs": int(report.get("counts", {}).get("verifiedPairCount", 0)),
        "frames_with_verified_edges": int(report.get("counts", {}).get("framesWithVerifiedEdges", 0)),
        "pose_rmse": stitched["pose_rmse"],
        "pose_median": stitched["pose_median"],
        "pose_p90": stitched["pose_p90"],
        "pose_p95": stitched["pose_p95"],
        "pose_max": stitched["pose_max"],
        "pose_sim3_scale": stitched["pose_sim3_scale"],
        "stitched": stitched,
        "per_window": per_window,
        "unstitched_local_windows_single_sim3": {
            "note": "diagnostic only; high values are expected because independent DA3 windows are local coordinate systems before bridge Sim3 stitching",
            "pose_rmse": float(np.sqrt(np.mean(unstitched_err * unstitched_err))),
            "pose_median": float(np.median(unstitched_err)),
            "pose_p90": float(np.percentile(unstitched_err, 90)),
            "pose_p95": float(np.percentile(unstitched_err, 95)),
            "pose_max": float(np.max(unstitched_err)),
            "pose_sim3_scale": float(unstitched_scale),
        },
        "per_frame": [
            {**row, "pose_error": float(value)}
            for row, value in zip(frame_rows, stitched["selected_order_errors"])
        ],
    }
    return metrics


def evaluate_per_window_pose(dtu_root: Path, scan: str, da3_out: Path) -> dict[str, Any]:
    report = read_json(da3_out / "mac_da3_window_reports.json")
    rows = []
    for window in report.get("windows", []):
        local_by_frame = load_window_centers(window, da3_out)
        pred, gt, frame_ids = centers_against_gt(dtu_root, local_by_frame)
        if len(frame_ids) < 3:
            continue
        err, scale = umeyama_align(pred, gt)
        rows.append(
            {
                "windowID": window.get("windowID"),
                "frame_count": len(frame_ids),
                "pose_rmse": float(np.sqrt(np.mean(err * err))),
                "pose_median": float(np.median(err)),
                "pose_p90": float(np.percentile(err, 90)),
                "pose_max": float(np.max(err)),
                "pose_sim3_scale": float(scale),
            }
        )
    all_err = np.asarray([value for row in rows for value in [row["pose_rmse"]]], dtype=np.float64)
    return {
        "window_count": len(rows),
        "mean_window_rmse": float(np.mean(all_err)) if all_err.size else math.nan,
        "max_window_rmse": float(np.max(all_err)) if all_err.size else math.nan,
        "windows": rows,
    }


def evaluate_stitched_windows(dtu_root: Path, scan: str, da3_out: Path, plan: dict[str, Any]) -> dict[str, Any]:
    report = read_json(da3_out / "mac_da3_window_reports.json")
    report_by_id = {str(window.get("windowID")): window for window in report.get("windows", [])}
    plan_windows = list(plan.get("windows", []))
    plan_by_id = {str(window.get("id")): window for window in plan_windows}
    local_by_window = {
        window_id: load_window_centers(report_by_id[window_id], da3_out)
        for window_id in report_by_id
    }
    global_by_window: dict[str, dict[str, np.ndarray]] = {}
    stitch_rows = []
    for index, plan_window in enumerate(plan_windows):
        window_id = str(plan_window.get("id"))
        local = local_by_window.get(window_id)
        if not local:
            continue
        if index == 0:
            global_by_window[window_id] = {fid: center.copy() for fid, center in local.items()}
            stitch_rows.append({"windowID": window_id, "status": "root", "bridge_count": 0})
            continue
        parent_id = str(plan_window.get("parentWindowID") or "")
        parent_global = global_by_window.get(parent_id)
        if parent_global is None:
            parent_id = next((candidate for candidate in reversed(list(global_by_window.keys()))), "")
            parent_global = global_by_window.get(parent_id)
        bridge_ids = [str(fid) for fid in plan_window.get("bridgeFrameIDs", [])]
        shared = [fid for fid in bridge_ids if fid in local and parent_global and fid in parent_global]
        if len(shared) < 3 and parent_global:
            shared = [fid for fid in local.keys() if fid in parent_global]
        if not parent_global or len(shared) < 3:
            # Keep the child local so diagnostics can reveal the failed bridge.
            global_by_window[window_id] = {fid: center.copy() for fid, center in local.items()}
            stitch_rows.append(
                {
                    "windowID": window_id,
                    "status": "failed_insufficient_bridge",
                    "parentWindowID": parent_id,
                    "bridge_count": len(shared),
                }
            )
            continue
        src = np.stack([local[fid] for fid in shared], axis=0)
        dst = np.stack([parent_global[fid] for fid in shared], axis=0)
        transform = estimate_sim3(src, dst)
        mapped = {fid: apply_sim3(center[None, :], transform)[0] for fid, center in local.items()}
        bridge_err = np.linalg.norm(apply_sim3(src, transform) - dst, axis=1)
        global_by_window[window_id] = mapped
        stitch_rows.append(
            {
                "windowID": window_id,
                "status": "stitched",
                "parentWindowID": parent_id,
                "bridge_count": len(shared),
                "bridge_rmse": float(np.sqrt(np.mean(bridge_err * bridge_err))),
                "bridge_p90": float(np.percentile(bridge_err, 90)),
                "sim3_scale": float(transform["scale"]),
            }
        )

    selected_global: dict[str, np.ndarray] = {}
    selected_source: dict[str, str] = {}
    for plan_window in plan_windows:
        window_id = str(plan_window.get("id"))
        mapped = global_by_window.get(window_id, {})
        for fid in [str(value) for value in plan_window.get("coreFrameIDs", [])]:
            if fid in mapped and fid not in selected_global:
                selected_global[fid] = mapped[fid]
                selected_source[fid] = window_id
    # If all frames are covered early, later windows may only be repeats; keep a
    # fallback so coverage metrics do not become hostage to core bookkeeping.
    for window_id, mapped in global_by_window.items():
        for fid, center in mapped.items():
            selected_global.setdefault(fid, center)
            selected_source.setdefault(fid, window_id)

    pred, gt, frame_ids = centers_against_gt(dtu_root, selected_global)
    err, scale = umeyama_align(pred, gt)
    return {
        "frame_count": len(frame_ids),
        "pose_rmse": float(np.sqrt(np.mean(err * err))),
        "pose_median": float(np.median(err)),
        "pose_p90": float(np.percentile(err, 90)),
        "pose_p95": float(np.percentile(err, 95)),
        "pose_max": float(np.max(err)),
        "pose_sim3_scale": float(scale),
        "stitch_edges": stitch_rows,
        "selected_order_frame_ids": frame_ids,
        "selected_order_window_ids": [selected_source[fid] for fid in frame_ids],
        "selected_order_errors": [float(value) for value in err],
    }


def load_window_centers(window: dict[str, Any], da3_out: Path) -> dict[str, np.ndarray]:
    centers: dict[str, np.ndarray] = {}
    for frame in window.get("frames", []):
        frame_id = str(frame.get("frameID"))
        if frame_id in centers:
            continue
        path = da3_out / str(frame["predExtrinsicsPath"])
        pred_ext = np.fromfile(path, dtype="<f4").reshape(3, 4)
        pred_w2c = np.eye(4, dtype=np.float64)
        pred_w2c[:3, :4] = pred_ext.astype(np.float64)
        centers[frame_id] = camera_center_from_w2c(pred_w2c)
    return centers


def centers_against_gt(dtu_root: Path, pred_by_frame: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    frame_ids = sorted(pred_by_frame.keys(), key=lambda value: int(value.rsplit("-", 1)[1]))
    pred = []
    gt = []
    for fid in frame_ids:
        dtu_idx = int(fid.rsplit("-", 1)[1])
        gt_ext, _ = parse_cam(dtu_root / "Cameras" / f"{dtu_idx:08d}_cam.txt")
        pred.append(pred_by_frame[fid])
        gt.append(camera_center_from_w2c(gt_ext))
    return np.stack(pred, axis=0), np.stack(gt, axis=0), frame_ids


def umeyama_align(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, float]:
    transform = estimate_sim3(src, dst)
    aligned = apply_sim3(src.astype(np.float64), transform)
    err = np.linalg.norm(aligned - dst.astype(np.float64), axis=1)
    return err, float(transform["scale"])


def estimate_sim3(src: np.ndarray, dst: np.ndarray) -> dict[str, Any]:
    src = src.astype(np.float64)
    dst = dst.astype(np.float64)
    mu_src = src.mean(axis=0)
    mu_dst = dst.mean(axis=0)
    src_c = src - mu_src
    dst_c = dst - mu_dst
    cov = (dst_c.T @ src_c) / max(len(src), 1)
    u, s, vt = np.linalg.svd(cov)
    d = np.ones(3)
    if np.linalg.det(u @ vt) < 0:
        d[-1] = -1.0
    r = u @ np.diag(d) @ vt
    var_src = float(np.mean(np.sum(src_c * src_c, axis=1)))
    scale = float(np.sum(s * d) / max(var_src, 1e-12))
    t = mu_dst - scale * (mu_src @ r.T)
    return {"scale": scale, "rotation": r, "translation": t}


def apply_sim3(points: np.ndarray, transform: dict[str, Any]) -> np.ndarray:
    return float(transform["scale"]) * (points.astype(np.float64) @ np.asarray(transform["rotation"], dtype=np.float64).T) + np.asarray(transform["translation"], dtype=np.float64)


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {}
    weighted_n = sum(int(r["frame_count"]) for r in results)
    all_err = np.asarray([e["pose_error"] for r in results for e in r["per_frame"]], dtype=np.float64)
    return {
        "scan_count": len(results),
        "frame_count": weighted_n,
        "mean_window_count": float(np.mean([r["window_count"] for r in results])),
        "mean_actual_slots": float(np.mean([r["actual_slots"] for r in results])),
        "pose_rmse": float(np.sqrt(np.mean(all_err * all_err))),
        "pose_median": float(np.median(all_err)),
        "pose_p90": float(np.percentile(all_err, 90)),
        "pose_p95": float(np.percentile(all_err, 95)),
        "pose_max": float(np.max(all_err)),
    }


def write_scan_summary(path: Path, metrics: dict[str, Any]) -> None:
    path.write_text(
        "\n".join(
            [
                f"# {metrics['scan']} COLMAP-385 Pose GT",
                "",
                f"- route: {metrics['route']}",
                f"- windows / slots: {metrics['window_count']} / {metrics['actual_slots']}",
                f"- selected / dropped frames: {metrics['selected_frame_count']} / {metrics['dropped_frame_count']}",
                f"- COLMAP verified pairs: {metrics['colmap_verified_pairs']}",
                f"- Pose RMSE: {metrics['pose_rmse']:.6f}",
                f"- Pose P90: {metrics['pose_p90']:.6f}",
                f"- Pose median: {metrics['pose_median']:.6f}",
                f"- Sim3 scale: {metrics['pose_sim3_scale']:.6f}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_overall_summary(path: Path, summary: dict[str, Any]) -> None:
    agg = summary["aggregate"]
    lines = [
        "# DTU64 COLMAP-385 Pose GT Summary",
        "",
        f"- route: {summary['route']}",
        f"- scans: {', '.join(summary['scans'])}",
        f"- bridge overlap: {summary['bridge_overlap']}",
        f"- elapsed: {summary['elapsed_s']:.3f}s",
        "",
        "| scan | windows | slots | selected | dropped | verified pairs | Pose RMSE | Pose P90 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summary["results"]:
        lines.append(
            f"| {r['scan']} | {r['window_count']} | {r['actual_slots']} | {r['selected_frame_count']} | "
            f"{r['dropped_frame_count']} | {r['colmap_verified_pairs']} | {r['pose_rmse']:.6f} | {r['pose_p90']:.6f} |"
        )
    lines += [
        "",
        f"Aggregate pose RMSE: {agg.get('pose_rmse', 0):.6f}",
        f"Aggregate pose P90: {agg.get('pose_p90', 0):.6f}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
