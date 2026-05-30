#!/usr/bin/env python3
"""Run DA3 multi-window routes on TartanGround pose/depth ground truth.

This research driver mirrors the TUM RGB-D GT benchmark, but adapts the
official TartanGround/TartanAir data layout:

  TartanGround RGBA-float depth + pose_[camera].txt
    -> PocketWorld-like capture manifests
    -> COLMAP-style DA3 window plans
    -> DA3-BASE K35@476x742 CoreML outputs
    -> pose/depth GT metrics and charts
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

import tum_rgbd_gt_benchmark as tum


RESEARCH_ROOT = Path(__file__).resolve().parents[2]
AETHER_ROOT = RESEARCH_ROOT.parent
DATASET_ROOT = AETHER_ROOT / "workspace/benchmark_dataset/tartanground"
COLMAP_EXECUTOR = RESEARCH_ROOT / "tools/python/colmap_view_graph_executor.py"
DA3_EXPORTER = RESEARCH_ROOT / "tools/python/da3_mac_window_export.py"
DEFAULT_MODEL = AETHER_ROOT / "pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage"
HF_REPO_ID = "theairlabcmu/TartanGround"
DEFAULT_CAMERA_NAMES = ["lcam_front"]
HORIZONTAL_CAMERA_NAMES = ["lcam_front", "lcam_left", "lcam_right", "lcam_back"]
TARTANGROUND_INTRINSICS = (320.0, 320.0, 319.5, 319.5)
TARTANGROUND_NED_R_CAM = np.asarray(
    [
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class TartanRecord:
    index: int
    frame_id: str
    frame_index: int
    camera_name: str
    timestamp: float
    image_path: Path
    depth_path: Path
    c2w_opencv: np.ndarray
    center: np.ndarray
    intrinsics: tuple[float, float, float, float]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--env", default="House")
    parser.add_argument("--version", default="omni", choices=["omni"])
    parser.add_argument("--traj", default="P0000")
    parser.add_argument("--camera-names", nargs="+", default=DEFAULT_CAMERA_NAMES)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--unzip", action="store_true")
    parser.add_argument("--max-frames", type=int, default=420)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--slot-targets", default="385,700")
    parser.add_argument("--bridge-overlap", type=int, default=6)
    parser.add_argument("--colmap-bin", default="colmap")
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--compute-unit", default="cpu", choices=["cpu", "cpu_and_gpu", "cpu_and_ne", "all"])
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--skip-da3", action="store_true")
    parser.add_argument("--skip-depth", action="store_true")
    parser.add_argument("--max-depth-frames", type=int, default=180)
    args = parser.parse_args()

    started = time.perf_counter()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    sequence = f"{args.env}_{args.version}_{args.traj}_{'-'.join(args.camera_names)}"
    traj_dir = ensure_tartanground_subset(
        dataset_root=args.dataset_root,
        env=args.env,
        version=args.version,
        traj=args.traj,
        camera_names=args.camera_names,
        download=args.download,
        unzip=args.unzip,
    )
    sequence_out = args.out_dir / sequence
    capture_dir = sequence_out / "capture_tartanground"
    colmap_out = sequence_out / "colmap_view_graph"
    prepare_tartanground_capture(
        traj_dir=traj_dir,
        sequence=sequence,
        camera_names=args.camera_names,
        capture_dir=capture_dir,
        max_frames=args.max_frames,
        frame_stride=args.frame_stride,
        force=not args.reuse,
    )
    run_colmap_plan(args, capture_dir, colmap_out)
    plan_summary = tum.read_json(colmap_out / "colmap_candidate_plan_summary.json")
    route_results = []
    for plan_info in plan_summary.get("planSummaries", []):
        actual_slots = int(plan_info["actualSlots"])
        overlay_dir = Path(plan_info["overlayDir"])
        da3_out = sequence_out / f"mac_da3_slots{actual_slots}"
        if args.skip_da3 and (da3_out / "depth_index.json").exists():
            metrics = evaluate_route(
                sequence=sequence,
                capture_dir=capture_dir,
                colmap_out=colmap_out,
                da3_out=da3_out,
                actual_slots=actual_slots,
                skip_depth=args.skip_depth,
                max_depth_frames=args.max_depth_frames,
            )
            metrics["da3_inference_status"] = "reused_existing_outputs_skip_da3"
        elif not args.skip_da3:
            run_da3(args, overlay_dir, da3_out)
            metrics = evaluate_route(
                sequence=sequence,
                capture_dir=capture_dir,
                colmap_out=colmap_out,
                da3_out=da3_out,
                actual_slots=actual_slots,
                skip_depth=args.skip_depth,
                max_depth_frames=args.max_depth_frames,
            )
        else:
            metrics = {
                "schema_version": "aether_tartanground_pose_depth_gt_metrics_v1",
                "sequence": sequence,
                "status": "plan_only_skip_da3",
                "actual_slots": actual_slots,
                "window_count": int(plan_info.get("windowCount", 0)),
                "selected_frame_count": int(plan_info.get("selectedFrameCount", 0)),
                "dropped_frame_count": int(plan_info.get("droppedFrameCount", 0)),
                "per_window": {},
                "stitched": {"selected_order_errors": []},
                "depth": {},
            }
        route_results.append(metrics)
        tum.write_json(sequence_out / f"pose_depth_gt_slots{actual_slots}.json", metrics)

    summary = {
        "schema_version": "aether_tartanground_da3_gt_benchmark_v1",
        "dataset": "TartanGround",
        "dataset_source": HF_REPO_ID,
        "dataset_route": f"{args.env}/Data_{args.version}/{args.traj}",
        "camera_names": args.camera_names,
        "route": "TartanGround -> COLMAP-style DA3 windows -> sealed DA3-BASE K35@476x742 -> pose/depth GT",
        "slot_targets": parse_slot_targets(args.slot_targets),
        "bridge_overlap": args.bridge_overlap,
        "elapsed_s": round(time.perf_counter() - started, 3),
        "results": [
            {
                "sequence": sequence,
                "elapsed_s": round(time.perf_counter() - started, 3),
                "routes": route_results,
            }
        ],
        "aggregate": tum.aggregate([{"sequence": sequence, "routes": route_results}]),
    }
    tum.write_json(args.out_dir / "summary.json", summary)
    write_overall_summary(args.out_dir / "summary.md", summary)
    write_summary_csv(args.out_dir / "summary.csv", summary)
    write_charts(args.out_dir, summary)
    print(json.dumps(summary["aggregate"], ensure_ascii=False, indent=2), flush=True)
    return 0


def ensure_tartanground_subset(
    *,
    dataset_root: Path,
    env: str,
    version: str,
    traj: str,
    camera_names: list[str],
    download: bool,
    unzip: bool,
) -> Path:
    traj_dir = dataset_root / env / f"Data_{version}" / traj
    patterns = [f"{env}/Data_{version}/{traj}/metadata.zip"]
    for camera_name in camera_names:
        patterns.append(f"{env}/Data_{version}/{traj}/image_{camera_name}.zip")
        patterns.append(f"{env}/Data_{version}/{traj}/depth_{camera_name}.zip")

    if download:
        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:  # pragma: no cover - depends on host env
            raise RuntimeError("huggingface_hub is required for --download") from exc
        dataset_root.mkdir(parents=True, exist_ok=True)
        snapshot_download(
            repo_id=HF_REPO_ID,
            repo_type="dataset",
            local_dir=str(dataset_root),
            allow_patterns=patterns,
        )

    missing = [pattern for pattern in patterns if not (dataset_root / pattern).exists()]
    if missing:
        raise FileNotFoundError(f"Missing TartanGround files: {missing[:8]}")

    if unzip:
        for pattern in patterns:
            zip_path = dataset_root / pattern
            with zipfile.ZipFile(zip_path) as archive:
                archive.extractall(zip_path.parent)

    for camera_name in camera_names:
        if not (traj_dir / f"image_{camera_name}").exists():
            raise FileNotFoundError(traj_dir / f"image_{camera_name}")
        if not (traj_dir / f"depth_{camera_name}").exists():
            raise FileNotFoundError(traj_dir / f"depth_{camera_name}")
        if not (traj_dir / f"pose_{camera_name}.txt").exists():
            raise FileNotFoundError(traj_dir / f"pose_{camera_name}.txt")
    return traj_dir


def prepare_tartanground_capture(
    *,
    traj_dir: Path,
    sequence: str,
    camera_names: list[str],
    capture_dir: Path,
    max_frames: int,
    frame_stride: int,
    force: bool,
) -> None:
    if capture_dir.exists() and force:
        shutil.rmtree(capture_dir)
    if (capture_dir / "photo_bundle.json").exists():
        return
    for name in ("photos_depth", "photos_highres", "previews"):
        (capture_dir / name).mkdir(parents=True, exist_ok=True)

    records = load_tartanground_records(
        traj_dir=traj_dir,
        sequence=sequence,
        camera_names=camera_names,
        max_frames=max_frames,
        frame_stride=frame_stride,
    )
    if len(records) < 35:
        raise RuntimeError(f"{sequence} has only {len(records)} associated frames")

    centers = np.stack([record.center for record in records], axis=0)
    scene_center = centers.mean(axis=0)
    edges = build_tartanground_pose_edges(records, centers)
    frames = []
    input_frames = []
    nodes = []
    gt_frames = []
    model = tum.da3_model_policy()
    for order, record in enumerate(records):
        image_name = f"{record.frame_id}.png"
        tum.link_or_copy(record.image_path, capture_dir / "photos_depth" / image_name)
        tum.link_or_copy(record.image_path, capture_dir / "photos_highres" / image_name)
        tum.write_preview(record.image_path, capture_dir / "previews" / image_name)
        with Image.open(record.image_path) as image:
            w, h = image.size
        fx, fy, cx, cy = record.intrinsics
        sx = 742.0 / float(w)
        sy = 476.0 / float(h)
        c2w_arkit = tum.opencv_c2w_to_arkit_c2w(record.c2w_opencv)
        azimuth, elevation = tum.camera_angles(record.center, scene_center)
        frames.append(
            {
                "id": record.frame_id,
                "highresFilename": image_name,
                "previewFilename": image_name,
                "timestamp": record.timestamp,
                "triggerTimestamp": record.timestamp,
                "azimuth": math.radians(azimuth),
                "elevation": math.radians(elevation),
                "captureKind": "tartanground_gt_research_frame",
                "poseSyncQuality": "tartanground_gt",
                "imageWidth": w,
                "imageHeight": h,
                "quality": {
                    "accepted": True,
                    "score": 1.0,
                    "viewGraphWeight": 1.0,
                    "kWindowWeight": 1.0,
                    "textureBestViewWeight": 1.0,
                    "rejectReasons": [],
                },
                "cameraTransform": c2w_arkit.reshape(-1, order="F").astype(float).tolist(),
                "intrinsics": [fx, fy, cx, cy],
                "cameraRadiusM": float(np.linalg.norm(record.center - scene_center)),
                "radiusShellID": "tartanground",
                "poseSource": "tartanground_gt",
                "trackingState": "normal",
                "cellID": f"tg_{record.camera_name}_{record.frame_index:06d}",
                "tartanIndex": record.index,
                "cameraName": record.camera_name,
                "sourceFrameIndex": record.frame_index,
            }
        )
        input_frames.append(
            {
                "id": record.frame_id,
                "sourceHighresRelativePath": f"photos_highres/{image_name}",
                "depthImageRelativePath": f"photos_depth/{image_name}",
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
                "id": record.frame_id,
                "timestamp": record.timestamp,
                "cellID": f"tg_{record.camera_name}_{record.frame_index:06d}",
                "azimuthDeg": azimuth,
                "elevationDeg": elevation,
            }
        )
        gt_frames.append(
            {
                "frameID": record.frame_id,
                "index": record.index,
                "sourceFrameIndex": record.frame_index,
                "cameraName": record.camera_name,
                "timestamp": record.timestamp,
                "imagePath": str(record.image_path),
                "depthPath": str(record.depth_path),
                "depthEncoding": "rgba_little_endian_float32_m",
                "depthScale": 1.0,
                "c2wOpenCV": record.c2w_opencv.reshape(-1).astype(float).tolist(),
                "center": record.center.astype(float).tolist(),
                "intrinsics": [fx, fy, cx, cy],
            }
        )

    tum.write_json(
        capture_dir / "photo_bundle.json",
        {
            "schemaVersion": "aether_photo_bundle_v1",
            "captureVersion": "tartanground_pose_depth_gt_research",
            "sourceKind": "tartanground",
            "photosHighresDir": "photos_highres",
            "previewsDir": "previews",
            "frames": frames,
        },
    )
    tum.write_json(
        capture_dir / "da3_input_manifest.json",
        {
            "schemaVersion": "aether_da3_input_manifest_v1",
            "sourceManifest": "photo_bundle.json",
            "photosDepthDir": "photos_depth",
            "model": model,
            "inputSizeLocked": True,
            "inputWidth": 742,
            "inputHeight": 476,
            "preprocessOwner": "research_tartanground_capture_adapter",
            "frameCount": len(input_frames),
            "frames": input_frames,
        },
    )
    tum.write_json(
        capture_dir / "view_graph.json",
        {
            "schemaVersion": "aether_view_graph_v1",
            "graphKind": "tartanground_pose_proxy_temporal_spatial_graph",
            "sourceManifest": "photo_bundle.json",
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "maxNeighborsPerNode": 64,
            "featureMatchStatus": "pending_colmap_executor",
            "nodes": nodes,
            "edges": edges,
            "summary": {"rule": "TartanGround GT pose proxy proposes COLMAP candidate pairs only"},
        },
    )
    tum.write_json(
        capture_dir / "model_policy.json",
        {
            "schemaVersion": "aether_model_policy_v1",
            "status": "locked",
            "selectedDepthModel": model,
            "rule": "research TartanGround GT benchmark",
        },
    )
    tum.write_json(capture_dir / "da3_k_windows.json", tum.seed_window_manifest(frames, model))
    tum.write_json(capture_dir / "bundle_validation.json", {"status": "ok", "frameCount": len(frames)})
    tum.write_json(
        capture_dir / "tartanground_gt_manifest.json",
        {
            "sequence": sequence,
            "trajDir": str(traj_dir),
            "cameraNames": camera_names,
            "cameraConvention": "TartanGround pose_[camera].txt in NED [x,y,z,qx,qy,qz,qw]; converted with official NED_R_cam to camera-in-world OpenCV-like c2w for DA3 input",
            "depthEncoding": "official reader: cv2 IMREAD_UNCHANGED RGBA view('<f4'), planar depth in meters",
            "frameCount": len(gt_frames),
            "frames": gt_frames,
        },
    )


def load_tartanground_records(
    *,
    traj_dir: Path,
    sequence: str,
    camera_names: list[str],
    max_frames: int,
    frame_stride: int,
) -> list[TartanRecord]:
    metadata = maybe_read_json(traj_dir / f"{traj_dir.name}_metadata.json")
    time_step = float(metadata.get("time_step") or 0.1)
    raw_records: list[TartanRecord] = []
    camera_order = {name: idx for idx, name in enumerate(camera_names)}
    for camera_name in camera_names:
        image_dir = traj_dir / f"image_{camera_name}"
        depth_dir = traj_dir / f"depth_{camera_name}"
        poses = np.loadtxt(traj_dir / f"pose_{camera_name}.txt", dtype=np.float64)
        if poses.ndim == 1:
            poses = poses[None, :]
        images = sorted(image_dir.glob(f"*_{camera_name}.png"))
        depths = sorted(depth_dir.glob(f"*_{camera_name}_depth.png"))
        image_by_index = {parse_frame_index(path.name): path for path in images}
        depth_by_index = {parse_frame_index(path.name): path for path in depths}
        frame_indices = sorted(set(image_by_index).intersection(depth_by_index))
        if frame_stride > 1:
            frame_indices = frame_indices[::frame_stride]
        for frame_index in frame_indices:
            if frame_index >= len(poses):
                continue
            pose = poses[frame_index]
            c2w = tartanground_pose_to_opencv_c2w(pose)
            timestamp = frame_index * time_step + camera_order[camera_name] * 1e-4
            frame_id = f"tg_{sequence}_{camera_name}_{frame_index:06d}"
            raw_records.append(
                TartanRecord(
                    index=0,
                    frame_id=frame_id,
                    frame_index=frame_index,
                    camera_name=camera_name,
                    timestamp=timestamp,
                    image_path=image_by_index[frame_index],
                    depth_path=depth_by_index[frame_index],
                    c2w_opencv=c2w,
                    center=c2w[:3, 3].copy(),
                    intrinsics=TARTANGROUND_INTRINSICS,
                )
            )
    raw_records.sort(key=lambda row: (row.frame_index, camera_order[row.camera_name]))
    if max_frames > 0 and len(raw_records) > max_frames:
        indices = np.linspace(0, len(raw_records) - 1, max_frames).round().astype(int)
        raw_records = [raw_records[int(i)] for i in sorted(set(indices.tolist()))]
    records = []
    for index, record in enumerate(raw_records):
        records.append(
            TartanRecord(
                index=index,
                frame_id=record.frame_id,
                frame_index=record.frame_index,
                camera_name=record.camera_name,
                timestamp=record.timestamp,
                image_path=record.image_path,
                depth_path=record.depth_path,
                c2w_opencv=record.c2w_opencv,
                center=record.center,
                intrinsics=record.intrinsics,
            )
        )
    return records


def parse_frame_index(name: str) -> int:
    return int(name.split("_", 1)[0])


def tartanground_pose_to_opencv_c2w(pose: np.ndarray) -> np.ndarray:
    tx, ty, tz, qx, qy, qz, qw = [float(value) for value in pose[:7]]
    c2w = np.eye(4, dtype=np.float64)
    c2w[:3, :3] = tum.quat_xyzw_to_rot(qx, qy, qz, qw) @ TARTANGROUND_NED_R_CAM
    c2w[:3, 3] = [tx, ty, tz]
    return c2w


def build_tartanground_pose_edges(records: list[TartanRecord], centers: np.ndarray) -> list[dict[str, Any]]:
    edge_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    max_dist = tum.max_pairwise_distance(centers)
    for i, record in enumerate(records):
        for j in range(i + 1, min(len(records), i + 49)):
            add_tartanground_edge(edge_by_pair, records, centers, i, j, max_dist, ["temporal_neighbor_proxy"])
    for i, center in enumerate(centers):
        dist = np.linalg.norm(centers - center[None, :], axis=1)
        nearest = [int(v) for v in np.argsort(dist)[1:33]]
        for j in nearest:
            if i < j:
                add_tartanground_edge(edge_by_pair, records, centers, i, j, max_dist, ["spatial_neighbor_proxy"])
            elif j < i:
                add_tartanground_edge(edge_by_pair, records, centers, j, i, max_dist, ["spatial_neighbor_proxy"])
    edges = list(edge_by_pair.values())
    edges.sort(key=lambda row: float(row["score"]), reverse=True)
    return edges


def add_tartanground_edge(
    edge_by_pair: dict[tuple[str, str], dict[str, Any]],
    records: list[TartanRecord],
    centers: np.ndarray,
    i: int,
    j: int,
    max_dist: float,
    reasons: list[str],
) -> None:
    a = records[i]
    b = records[j]
    baseline = float(np.linalg.norm(centers[i] - centers[j]))
    temporal_gap = float(abs(b.timestamp - a.timestamp))
    orientation_gap = tum.rotation_angle_degrees(a.c2w_opencv[:3, :3], b.c2w_opencv[:3, :3])
    baseline_score = max(0.0, 1.0 - baseline / max(max_dist, 1e-6))
    temporal_score = max(0.0, 1.0 - temporal_gap / 4.0)
    orientation_score = max(0.0, 1.0 - orientation_gap / 140.0)
    same_source_frame = a.frame_index == b.frame_index and a.camera_name != b.camera_name
    rig_score = 0.20 if same_source_frame else 0.0
    score = 0.40 * baseline_score + 0.30 * temporal_score + 0.20 * orientation_score + rig_score
    key = tuple(sorted((a.frame_id, b.frame_id)))
    existing = edge_by_pair.get(key)
    if existing is not None and float(existing["score"]) >= score:
        return
    edge_by_pair[key] = {
        "sourceID": a.frame_id,
        "targetID": b.frame_id,
        "score": float(score),
        "angularGapDeg": float(orientation_gap),
        "baselineM": float(baseline),
        "radiusRatio": float(baseline / max(max_dist, 1e-6)),
        "temporalGapSec": temporal_gap,
        "overlapProxy": float(max(temporal_score, baseline_score)),
        "sameRadiusShell": True,
        "supportKind": "tartanground_pose_proxy",
        "reasons": sorted(set((existing or {}).get("reasons", []) + reasons + (["same_rig_timestamp"] if same_source_frame else []))),
    }


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
        args.slot_targets,
        "--bridge-overlap",
        str(args.bridge_overlap),
        "--view-graph-top-k",
        "18",
        "--temporal-neighbors",
        "10",
        "--max-image-size",
        "1000",
        "--max-num-features",
        "4096",
    ]
    if args.reuse:
        command.append("--reuse")
    tum.run_command(command, colmap_out / "driver_log.jsonl", "colmap_plan")


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
    tum.run_command(command, da3_out / "driver_log.jsonl", "da3_coreml")


def evaluate_route(
    *,
    sequence: str,
    capture_dir: Path,
    colmap_out: Path,
    da3_out: Path,
    actual_slots: int,
    skip_depth: bool,
    max_depth_frames: int,
) -> dict[str, Any]:
    plan = tum.read_json(colmap_out / f"da3_k_windows_colmap_slots{actual_slots}.json")
    report = tum.read_json(colmap_out / "colmap_view_graph_report.json")
    if not (da3_out / "depth_index.json").exists():
        raise FileNotFoundError(da3_out / "depth_index.json")
    per_window = evaluate_per_window_pose(capture_dir, da3_out)
    stitched = evaluate_stitched_windows(capture_dir, da3_out, plan)
    official_streaming = tum.evaluate_official_streaming_alignment(
        capture_dir,
        da3_out,
        plan,
        centers_against_gt_fn=centers_against_gt,
    )
    official_streaming_loop = tum.evaluate_official_streaming_loop_alignment(
        capture_dir,
        da3_out,
        plan,
        centers_against_gt_fn=centers_against_gt,
    )
    depth_metrics = {} if skip_depth else evaluate_depth_gt(capture_dir, da3_out, max_depth_frames=max_depth_frames)
    return {
        "schema_version": "aether_tartanground_pose_depth_gt_metrics_v1",
        "sequence": sequence,
        "route": f"COLMAP slots{actual_slots} + DA3-BASE K35@476x742",
        "actual_slots": actual_slots,
        "window_count": int(plan.get("windowCount", 0)),
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
        "per_window": per_window,
        "stitched": stitched,
        "official_streaming": official_streaming,
        "official_streaming_loop": official_streaming_loop,
        "depth": depth_metrics,
    }


def evaluate_per_window_pose(capture_dir: Path, da3_out: Path) -> dict[str, Any]:
    report = tum.read_json(da3_out / "mac_da3_window_reports.json")
    rows = []
    for window in report.get("windows", []):
        local_by_frame = tum.load_window_centers(window, da3_out)
        pred, gt, frame_ids = centers_against_gt(capture_dir, local_by_frame)
        if len(frame_ids) < 3:
            continue
        err, scale, _ = tum.umeyama_align(pred, gt)
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
    rmse = np.asarray([float(row["pose_rmse"]) for row in rows], dtype=np.float64)
    return {
        "window_count": len(rows),
        "mean_window_rmse": float(np.mean(rmse)) if rmse.size else math.nan,
        "max_window_rmse": float(np.max(rmse)) if rmse.size else math.nan,
        "windows": rows,
    }


def evaluate_stitched_windows(capture_dir: Path, da3_out: Path, plan: dict[str, Any]) -> dict[str, Any]:
    report = tum.read_json(da3_out / "mac_da3_window_reports.json")
    report_by_id = {str(window.get("windowID")): window for window in report.get("windows", [])}
    plan_windows = list(plan.get("windows", []))
    local_by_window = {
        window_id: tum.load_window_centers(report_by_id[window_id], da3_out)
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
            shared = [fid for fid in local if fid in parent_global]
        if not parent_global or len(shared) < 3:
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
        transform = tum.estimate_sim3(src, dst)
        mapped = {fid: tum.apply_sim3(center[None, :], transform)[0] for fid, center in local.items()}
        bridge_err = np.linalg.norm(tum.apply_sim3(src, transform) - dst, axis=1)
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
    for window_id, mapped in global_by_window.items():
        for fid, center in mapped.items():
            selected_global.setdefault(fid, center)
            selected_source.setdefault(fid, window_id)

    pred, gt, frame_ids = centers_against_gt(capture_dir, selected_global)
    err, scale, aligned = tum.umeyama_align(pred, gt)
    return {
        "frame_count": len(frame_ids),
        "pose_rmse": float(np.sqrt(np.mean(err * err))),
        "pose_median": float(np.median(err)),
        "pose_p90": float(np.percentile(err, 90)),
        "pose_p95": float(np.percentile(err, 95)),
        "pose_max": float(np.max(err)),
        "pose_sim3_scale": float(scale),
        "bridge_scale_mean": tum.safe_mean([row.get("sim3_scale") for row in stitch_rows if "sim3_scale" in row]),
        "bridge_scale_std": tum.safe_std([row.get("sim3_scale") for row in stitch_rows if "sim3_scale" in row]),
        "stitch_edges": stitch_rows,
        "selected_order_frame_ids": frame_ids,
        "selected_order_window_ids": [selected_source[fid] for fid in frame_ids],
        "selected_order_errors": [float(value) for value in err],
        "trajectory": [
            {
                "frameID": fid,
                "windowID": selected_source[fid],
                "gt": gt_i.astype(float).tolist(),
                "predAligned": pred_i.astype(float).tolist(),
                "poseError": float(e),
            }
            for fid, gt_i, pred_i, e in zip(frame_ids, gt, aligned, err)
        ],
    }


def centers_against_gt(capture_dir: Path, pred_by_frame: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    gt_manifest = tum.read_json(capture_dir / "tartanground_gt_manifest.json")
    gt_by_frame = {str(frame["frameID"]): np.asarray(frame["center"], dtype=np.float64) for frame in gt_manifest.get("frames", [])}
    frame_order = {str(frame["frameID"]): int(frame["index"]) for frame in gt_manifest.get("frames", [])}
    frame_ids = sorted(pred_by_frame.keys(), key=lambda fid: frame_order.get(fid, 10**9))
    pred = []
    gt = []
    kept = []
    for frame_id in frame_ids:
        if frame_id not in gt_by_frame:
            continue
        pred.append(pred_by_frame[frame_id])
        gt.append(gt_by_frame[frame_id])
        kept.append(frame_id)
    if not kept:
        raise RuntimeError("No predicted frames overlap TartanGround GT")
    return np.stack(pred, axis=0), np.stack(gt, axis=0), kept


def evaluate_depth_gt(capture_dir: Path, da3_out: Path, *, max_depth_frames: int) -> dict[str, Any]:
    gt_manifest = tum.read_json(capture_dir / "tartanground_gt_manifest.json")
    gt_by_frame = {str(frame["frameID"]): frame for frame in gt_manifest.get("frames", [])}
    depth_index = tum.read_json(da3_out / "depth_index.json")
    rows = list(depth_index.get("frames", []))
    if max_depth_frames > 0 and len(rows) > max_depth_frames:
        idx = np.linspace(0, len(rows) - 1, max_depth_frames).round().astype(int)
        rows = [rows[int(i)] for i in sorted(set(idx.tolist()))]
    raw_pairs = collect_depth_pairs(rows, gt_by_frame, da3_out, inverse=False)
    inv_pairs = collect_depth_pairs(rows, gt_by_frame, da3_out, inverse=True)
    raw_metrics = depth_metrics_from_pairs(raw_pairs, mapping="depth")
    inv_metrics = depth_metrics_from_pairs(inv_pairs, mapping="inverse_depth")
    best = raw_metrics if raw_metrics["abs_rel"] <= inv_metrics["abs_rel"] else inv_metrics
    per_frame = depth_per_frame_metrics(rows, gt_by_frame, da3_out, inverse=best["mapping"] == "inverse_depth")
    return {
        "frame_count": len(rows),
        "pixel_sample_count": int(len(raw_pairs[0])) if raw_pairs[0].size else 0,
        "best_mapping": best["mapping"],
        "global_scale": best,
        "raw_depth_global_scale": raw_metrics,
        "inverse_depth_global_scale": inv_metrics,
        "per_frame_scale_mean": tum.aggregate_depth_rows(per_frame),
        "per_frame": per_frame[:80],
    }


def collect_depth_pairs(
    rows: list[dict[str, Any]],
    gt_by_frame: dict[str, dict[str, Any]],
    da3_out: Path,
    *,
    inverse: bool,
) -> tuple[np.ndarray, np.ndarray]:
    pred_values = []
    gt_values = []
    for row in rows:
        frame_id = str(row["frameID"])
        gt_row = gt_by_frame.get(frame_id)
        if not gt_row:
            continue
        h = int(row.get("depthHeight") or 476)
        w = int(row.get("depthWidth") or 742)
        pred = np.fromfile(da3_out / str(row["relativeDepthPath"]), dtype="<f4").reshape(h, w).astype(np.float32)
        if inverse:
            pred = 1.0 / np.maximum(pred, 1e-6)
        gt = load_gt_depth(Path(str(gt_row["depthPath"])), h, w)
        valid = np.isfinite(pred) & np.isfinite(gt) & (pred > 0.0) & (gt > 0.05) & (gt < 80.0)
        ys, xs = np.where(valid)
        if len(xs) == 0:
            continue
        step = max(1, len(xs) // 1800)
        pred_values.append(pred[ys[::step], xs[::step]])
        gt_values.append(gt[ys[::step], xs[::step]])
    if not pred_values:
        return np.asarray([], dtype=np.float32), np.asarray([], dtype=np.float32)
    return np.concatenate(pred_values).astype(np.float64), np.concatenate(gt_values).astype(np.float64)


def depth_metrics_from_pairs(pair: tuple[np.ndarray, np.ndarray], *, mapping: str) -> dict[str, Any]:
    return tum.depth_metrics_from_pairs(pair, mapping=mapping)


def depth_per_frame_metrics(
    rows: list[dict[str, Any]],
    gt_by_frame: dict[str, dict[str, Any]],
    da3_out: Path,
    *,
    inverse: bool,
) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        frame_id = str(row["frameID"])
        gt_row = gt_by_frame.get(frame_id)
        if not gt_row:
            continue
        h = int(row.get("depthHeight") or 476)
        w = int(row.get("depthWidth") or 742)
        pred = np.fromfile(da3_out / str(row["relativeDepthPath"]), dtype="<f4").reshape(h, w).astype(np.float32)
        if inverse:
            pred = 1.0 / np.maximum(pred, 1e-6)
        gt = load_gt_depth(Path(str(gt_row["depthPath"])), h, w)
        valid = np.isfinite(pred) & np.isfinite(gt) & (pred > 0.0) & (gt > 0.05) & (gt < 80.0)
        if int(valid.sum()) < 200:
            continue
        p = pred[valid].astype(np.float64)
        g = gt[valid].astype(np.float64)
        step = max(1, p.size // 2000)
        metrics = depth_metrics_from_pairs((p[::step], g[::step]), mapping="per_frame_inverse_depth" if inverse else "per_frame_depth")
        out.append({"frameID": frame_id, "windowID": row.get("windowID"), **metrics})
    return out


def load_gt_depth(path: Path, height: int, width: int) -> np.ndarray:
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(path)
    if raw.ndim == 3:
        depth_m = np.squeeze(raw.view("<f4"), axis=-1).astype(np.float32)
    else:
        depth_m = raw.astype(np.float32)
    if depth_m.shape != (height, width):
        depth_m = cv2.resize(depth_m, (width, height), interpolation=cv2.INTER_NEAREST)
    return depth_m


def write_overall_summary(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# TartanGround DA3 Multi-Window GT Benchmark",
        "",
        f"- route: {summary['route']}",
        f"- dataset route: {summary['dataset_route']}",
        f"- camera names: {', '.join(summary['camera_names'])}",
        f"- bridge overlap: {summary['bridge_overlap']}",
        "",
        "| sequence | route | windows | selected | dropped | local RMSE | bridge RMSE | bridge P90 | dense Sim3 RMSE | dense Sim3 P90 | dense+loop RMSE | dense+loop P90 | loop constraints | depth AbsRel | depth P90 m | verified pairs |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for seq in summary.get("results", []):
        for route in seq.get("routes", []):
            depth = route.get("depth", {}).get("global_scale", {})
            lines.append(
                "| {sequence} | slots{actual_slots} | {window_count} | {selected_frame_count} | {dropped_frame_count} | "
                "{local:.6f} | {pose_rmse:.6f} | {pose_p90:.6f} | {official_rmse:.6f} | {official_p90:.6f} | {loop_rmse:.6f} | {loop_p90:.6f} | {loop_constraints} | {abs_rel:.6f} | {p90_abs:.6f} | {verified} |".format(
                    sequence=seq["sequence"],
                    actual_slots=route["actual_slots"],
                    window_count=route["window_count"],
                    selected_frame_count=route["selected_frame_count"],
                    dropped_frame_count=route["dropped_frame_count"],
                    local=float(route["per_window"].get("mean_window_rmse", math.nan)),
                    pose_rmse=float(route.get("pose_rmse", math.nan)),
                    pose_p90=float(route.get("pose_p90", math.nan)),
                    official_rmse=float(route.get("official_streaming", {}).get("pose_rmse", math.nan)),
                    official_p90=float(route.get("official_streaming", {}).get("pose_p90", math.nan)),
                    loop_rmse=float(route.get("official_streaming_loop", {}).get("pose_rmse", math.nan)),
                    loop_p90=float(route.get("official_streaming_loop", {}).get("pose_p90", math.nan)),
                    loop_constraints=int(route.get("official_streaming_loop", {}).get("loop_constraint_count", 0)),
                    abs_rel=float(depth.get("abs_rel", math.nan)),
                    p90_abs=float(depth.get("p90_abs_m", math.nan)),
                    verified=int(route.get("colmap_verified_pairs", 0)),
                )
            )
    lines.extend(
        [
            "",
            "Charts:",
            "",
            "- `charts/pose_rmse_p90.png`",
            "- `charts/depth_absrel_p90.png`",
            "- `charts/trajectory_topdown.png`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_csv(path: Path, summary: dict[str, Any]) -> None:
    rows = []
    for seq in summary.get("results", []):
        for route in seq.get("routes", []):
            depth = route.get("depth", {}).get("global_scale", {})
            rows.append(
                {
                    "sequence": seq["sequence"],
                    "camera_names": ",".join(summary.get("camera_names", [])),
                    "actual_slots": route["actual_slots"],
                    "window_count": route["window_count"],
                    "selected_frame_count": route["selected_frame_count"],
                    "dropped_frame_count": route["dropped_frame_count"],
                    "local_rmse": route["per_window"].get("mean_window_rmse"),
                    "stitched_rmse": route.get("pose_rmse"),
                    "stitched_p90": route.get("pose_p90"),
                    "bridge_scale_std": route["stitched"].get("bridge_scale_std"),
                    "official_streaming_rmse": route.get("official_streaming", {}).get("pose_rmse"),
                    "official_streaming_p90": route.get("official_streaming", {}).get("pose_p90"),
                    "official_streaming_bridge_scale_std": route.get("official_streaming", {}).get("bridge_scale_std"),
                    "official_streaming_loop_rmse": route.get("official_streaming_loop", {}).get("pose_rmse"),
                    "official_streaming_loop_p90": route.get("official_streaming_loop", {}).get("pose_p90"),
                    "official_streaming_loop_constraints": route.get("official_streaming_loop", {}).get("loop_constraint_count"),
                    "official_streaming_loop_status": route.get("official_streaming_loop", {}).get("status"),
                    "depth_mapping": depth.get("mapping"),
                    "depth_abs_rel": depth.get("abs_rel"),
                    "depth_rmse_m": depth.get("rmse_m"),
                    "depth_p90_abs_m": depth.get("p90_abs_m"),
                    "colmap_verified_pairs": route.get("colmap_verified_pairs"),
                    "frames_with_verified_edges": route.get("frames_with_verified_edges"),
                }
            )
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_charts(out_dir: Path, summary: dict[str, Any]) -> None:
    chart_dir = out_dir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for seq in summary.get("results", []):
        for route in seq.get("routes", []):
            rows.append((f"{seq['sequence']}\nslots{route['actual_slots']}", route))
    if not rows:
        return
    labels = [row[0].replace("\n", " ") for row in rows]
    tum.draw_grouped_bar_chart(
        chart_dir / "pose_rmse_p90.png",
        title="TartanGround pose GT",
        labels=labels,
        series=[
            ("local RMSE", [row[1]["per_window"].get("mean_window_rmse", math.nan) for row in rows], (67, 116, 179)),
            ("stitched RMSE", [row[1].get("pose_rmse", math.nan) for row in rows], (213, 94, 0)),
            ("stitched P90", [row[1].get("pose_p90", math.nan) for row in rows], (45, 45, 45)),
        ],
        y_label="camera center error after Sim3",
    )
    tum.draw_grouped_bar_chart(
        chart_dir / "depth_absrel_p90.png",
        title="TartanGround depth GT",
        labels=labels,
        series=[
            ("AbsRel", [row[1].get("depth", {}).get("global_scale", {}).get("abs_rel", math.nan) for row in rows], (0, 158, 115)),
            ("P90 abs m", [row[1].get("depth", {}).get("global_scale", {}).get("p90_abs_m", math.nan) for row in rows], (204, 121, 167)),
        ],
        y_label="depth GT metric",
    )
    trajectory = rows[0][1].get("stitched", {}).get("trajectory", [])
    if trajectory:
        gt = np.asarray([row["gt"] for row in trajectory], dtype=np.float64)
        pred = np.asarray([row["predAligned"] for row in trajectory], dtype=np.float64)
        tum.draw_trajectory_chart(chart_dir / "trajectory_topdown.png", gt, pred)


def parse_slot_targets(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def maybe_read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
