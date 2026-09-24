#!/usr/bin/env python3
"""Run DA3 multi-window routes on TUM RGB-D pose/depth ground truth.

This is a research-only driver. It downloads/prepares TUM RGB-D sequences as
PocketWorld-like captures, lets the existing COLMAP-style executor propose
DA3 windows, runs the sealed DA3-BASE K35@476x742 CoreML executor, and scores
stitched camera centers plus depth maps against TUM metric GT.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.request import urlretrieve

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


RESEARCH_ROOT = Path(__file__).resolve().parents[2]
AETHER_ROOT = RESEARCH_ROOT.parent
DATASET_ROOT = AETHER_ROOT / "workspace/benchmark_dataset/tum_rgbd"
COLMAP_EXECUTOR = RESEARCH_ROOT / "tools/python/colmap_view_graph_executor.py"
DA3_EXPORTER = RESEARCH_ROOT / "tools/python/da3_mac_window_export.py"
DEFAULT_MODEL = AETHER_ROOT / "pocketworld_flutter/ios/Runner/Models/DA3-BASE-CoreML/DA3BASE_476x742_N35_pose.mlpackage"
OFFICIAL_DA3_STREAMING_VENDOR = RESEARCH_ROOT / "tools/vendor/official_da3_streaming"

TUM_SEQUENCES: dict[str, dict[str, Any]] = {
    "freiburg1_desk": {
        "url": "https://cvg.cit.tum.de/rgbd/dataset/freiburg1/rgbd_dataset_freiburg1_desk.tgz",
        "folder": "rgbd_dataset_freiburg1_desk",
        "family": "freiburg1",
    },
    "freiburg1_room": {
        "url": "https://cvg.cit.tum.de/rgbd/dataset/freiburg1/rgbd_dataset_freiburg1_room.tgz",
        "folder": "rgbd_dataset_freiburg1_room",
        "family": "freiburg1",
    },
    "freiburg2_desk": {
        "url": "https://cvg.cit.tum.de/rgbd/dataset/freiburg2/rgbd_dataset_freiburg2_desk.tgz",
        "folder": "rgbd_dataset_freiburg2_desk",
        "family": "freiburg2",
    },
}

TUM_INTRINSICS = {
    "freiburg1": (517.3, 516.5, 318.6, 255.3),
    "freiburg2": (520.9, 521.0, 325.1, 249.7),
    "freiburg3": (535.4, 539.2, 320.1, 247.6),
}


@dataclass(frozen=True)
class TumRecord:
    index: int
    frame_id: str
    rgb_timestamp: float
    depth_timestamp: float
    gt_timestamp: float
    rgb_path: Path
    depth_path: Path
    c2w_opencv: np.ndarray
    center: np.ndarray
    intrinsics: tuple[float, float, float, float]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=DATASET_ROOT)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--sequences", nargs="+", default=["freiburg1_desk"])
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--max-frames", type=int, default=420)
    parser.add_argument("--frame-stride", type=int, default=1)
    parser.add_argument("--slot-targets", default="385,700")
    parser.add_argument("--bridge-overlap", type=int, default=6)
    parser.add_argument("--colmap-bin", default="colmap")
    parser.add_argument("--python-bin", default=sys.executable)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--compute-unit", default="all", choices=["cpu", "cpu_and_gpu", "cpu_and_ne", "all"])
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--skip-da3", action="store_true")
    parser.add_argument("--skip-depth", action="store_true")
    parser.add_argument("--max-depth-frames", type=int, default=180)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    sequence_results: list[dict[str, Any]] = []
    for sequence in args.sequences:
        sequence_started = time.perf_counter()
        dataset_dir = ensure_tum_sequence(args.dataset_root, sequence, download=args.download)
        sequence_out = args.out_dir / sequence
        capture_dir = sequence_out / "capture_tum_rgbd"
        colmap_out = sequence_out / "colmap_view_graph"
        prepare_tum_capture(
            dataset_dir=dataset_dir,
            sequence=sequence,
            capture_dir=capture_dir,
            max_frames=args.max_frames,
            frame_stride=args.frame_stride,
            force=not args.reuse,
        )
        run_colmap_plan(args, capture_dir, colmap_out)
        plan_summary = read_json(colmap_out / "colmap_candidate_plan_summary.json")
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
                    "schema_version": "aether_tum_rgbd_pose_depth_gt_metrics_v1",
                    "sequence": sequence,
                    "route": f"COLMAP slots{actual_slots} + DA3-BASE K35@476x742",
                    "status": "plan_only_skip_da3",
                    "actual_slots": actual_slots,
                    "window_count": int(plan_info.get("windowCount", 0)),
                    "selected_frame_count": int(plan_info.get("selectedFrameCount", 0)),
                    "dropped_frame_count": int(plan_info.get("droppedFrameCount", 0)),
                    "per_window": {},
                    "stitched": {"selected_order_errors": []},
                    "depth": {},
                }
            metrics["elapsed_s"] = round(time.perf_counter() - sequence_started, 3)
            route_results.append(metrics)
            write_json(sequence_out / f"pose_depth_gt_slots{actual_slots}.json", metrics)
        sequence_result = {
            "sequence": sequence,
            "elapsed_s": round(time.perf_counter() - sequence_started, 3),
            "routes": route_results,
        }
        sequence_results.append(sequence_result)
        write_sequence_summary(sequence_out / "summary.md", sequence_result)

    summary = {
        "schema_version": "aether_tum_rgbd_da3_gt_benchmark_v1",
        "dataset": "TUM RGB-D",
        "dataset_license": "TUM RGB-D public research dataset; reported by TUM as Creative Commons Attribution 4.0 in dataset citation pages",
        "route": "TUM RGB-D -> COLMAP-style DA3 windows -> sealed DA3-BASE K35@476x742 -> pose/depth GT",
        "sequences": args.sequences,
        "slot_targets": parse_slot_targets(args.slot_targets),
        "bridge_overlap": args.bridge_overlap,
        "elapsed_s": round(time.perf_counter() - started, 3),
        "results": sequence_results,
        "aggregate": aggregate(sequence_results),
    }
    write_json(args.out_dir / "summary.json", summary)
    write_overall_summary(args.out_dir / "summary.md", summary)
    write_summary_csv(args.out_dir / "summary.csv", summary)
    write_charts(args.out_dir, summary)
    print(json.dumps(summary["aggregate"], ensure_ascii=False, indent=2), flush=True)
    return 0


def ensure_tum_sequence(dataset_root: Path, sequence: str, *, download: bool) -> Path:
    if sequence not in TUM_SEQUENCES:
        raise ValueError(f"Unknown TUM sequence {sequence}. Known: {sorted(TUM_SEQUENCES)}")
    meta = TUM_SEQUENCES[sequence]
    folder = dataset_root / str(meta["folder"])
    if (folder / "rgb.txt").exists():
        return folder
    if not download:
        raise FileNotFoundError(f"{folder} is missing. Re-run with --download.")
    dataset_root.mkdir(parents=True, exist_ok=True)
    archive = dataset_root / f"{meta['folder']}.tgz"
    if not archive.exists():
        print(f"Downloading {sequence} -> {archive}", flush=True)
        urlretrieve(str(meta["url"]), archive)
    print(f"Extracting {archive}", flush=True)
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(dataset_root)
    if not (folder / "rgb.txt").exists():
        raise FileNotFoundError(folder / "rgb.txt")
    return folder


def prepare_tum_capture(
    *,
    dataset_dir: Path,
    sequence: str,
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

    records = load_tum_records(dataset_dir, sequence, max_frames=max_frames, frame_stride=frame_stride)
    if len(records) < 35:
        raise RuntimeError(f"{sequence} has only {len(records)} associated frames")

    centers = np.stack([record.center for record in records], axis=0)
    scene_center = centers.mean(axis=0)
    edges = build_tum_pose_edges(records, centers)
    frames = []
    input_frames = []
    nodes = []
    gt_frames = []
    model = da3_model_policy()
    for order, record in enumerate(records):
        image_name = f"{record.frame_id}.png"
        link_or_copy(record.rgb_path, capture_dir / "photos_depth" / image_name)
        link_or_copy(record.rgb_path, capture_dir / "photos_highres" / image_name)
        write_preview(record.rgb_path, capture_dir / "previews" / image_name)
        with Image.open(record.rgb_path) as image:
            w, h = image.size
        fx, fy, cx, cy = record.intrinsics
        sx = 742.0 / float(w)
        sy = 476.0 / float(h)
        c2w_arkit = opencv_c2w_to_arkit_c2w(record.c2w_opencv)
        azimuth, elevation = camera_angles(record.center, scene_center)
        quality_score = 1.0
        frames.append(
            {
                "id": record.frame_id,
                "highresFilename": image_name,
                "previewFilename": image_name,
                "timestamp": record.rgb_timestamp,
                "triggerTimestamp": record.rgb_timestamp,
                "azimuth": math.radians(azimuth),
                "elevation": math.radians(elevation),
                "captureKind": "tum_rgbd_gt_research_frame",
                "poseSyncQuality": "tum_mocap_gt",
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
                "radiusShellID": "tum_rgbd",
                "poseSource": "tum_mocap_gt",
                "trackingState": "normal",
                "cellID": f"tum_{sequence}_{order:04d}",
                "tumIndex": record.index,
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
                "timestamp": record.rgb_timestamp,
                "cellID": f"tum_{sequence}_{order:04d}",
                "azimuthDeg": azimuth,
                "elevationDeg": elevation,
            }
        )
        gt_frames.append(
            {
                "frameID": record.frame_id,
                "index": record.index,
                "rgbTimestamp": record.rgb_timestamp,
                "depthTimestamp": record.depth_timestamp,
                "gtTimestamp": record.gt_timestamp,
                "rgbPath": str(record.rgb_path),
                "depthPath": str(record.depth_path),
                "depthScale": 5000.0,
                "c2wOpenCV": record.c2w_opencv.reshape(-1).astype(float).tolist(),
                "center": record.center.astype(float).tolist(),
                "intrinsics": [fx, fy, cx, cy],
            }
        )

    write_json(
        capture_dir / "photo_bundle.json",
        {
            "schemaVersion": "aether_photo_bundle_v1",
            "captureVersion": "tum_rgbd_pose_depth_gt_research",
            "sourceKind": "tum_rgbd",
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
            "preprocessOwner": "research_tum_rgbd_capture_adapter",
            "frameCount": len(input_frames),
            "frames": input_frames,
        },
    )
    write_json(
        capture_dir / "view_graph.json",
        {
            "schemaVersion": "aether_view_graph_v1",
            "graphKind": "tum_rgbd_pose_proxy_temporal_spatial_graph",
            "sourceManifest": "photo_bundle.json",
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "maxNeighborsPerNode": 48,
            "featureMatchStatus": "pending_colmap_executor",
            "nodes": nodes,
            "edges": edges,
            "summary": {"rule": "TUM GT pose proxy proposes COLMAP candidate pairs only"},
        },
    )
    write_json(
        capture_dir / "model_policy.json",
        {
            "schemaVersion": "aether_model_policy_v1",
            "status": "locked",
            "selectedDepthModel": model,
            "rule": "research TUM RGB-D GT benchmark",
        },
    )
    write_json(capture_dir / "da3_k_windows.json", seed_window_manifest(frames, model))
    write_json(capture_dir / "bundle_validation.json", {"status": "ok", "frameCount": len(frames)})
    write_json(
        capture_dir / "tum_rgbd_gt_manifest.json",
        {
            "sequence": sequence,
            "datasetDir": str(dataset_dir),
            "cameraConvention": "TUM color camera c2w in OpenCV optical frame; app adapter stores ARKit-compatible c2w only for DA3 executor input",
            "frameCount": len(gt_frames),
            "frames": gt_frames,
        },
    )


def load_tum_records(dataset_dir: Path, sequence: str, *, max_frames: int, frame_stride: int) -> list[TumRecord]:
    meta = TUM_SEQUENCES[sequence]
    family = str(meta["family"])
    intrinsics = TUM_INTRINSICS[family]
    rgb = read_tum_file_list(dataset_dir / "rgb.txt")
    depth = read_tum_file_list(dataset_dir / "depth.txt")
    gt = read_tum_file_list(dataset_dir / "groundtruth.txt", values_per_row=7)
    rgb_depth = associate(rgb, depth, max_difference=0.025)
    rgb_gt = associate({a: rgb[a] for a, _ in rgb_depth}, gt, max_difference=0.04)
    depth_by_rgb = {a: b for a, b in rgb_depth}
    gt_by_rgb = {a: b for a, b in rgb_gt}
    rgb_times = sorted(set(depth_by_rgb).intersection(gt_by_rgb))
    if frame_stride > 1:
        rgb_times = rgb_times[::frame_stride]
    if max_frames > 0 and len(rgb_times) > max_frames:
        indices = np.linspace(0, len(rgb_times) - 1, max_frames).round().astype(int)
        rgb_times = [rgb_times[int(i)] for i in sorted(set(indices.tolist()))]
    records: list[TumRecord] = []
    for index, rgb_ts in enumerate(rgb_times):
        depth_ts = depth_by_rgb[rgb_ts]
        gt_ts = gt_by_rgb[rgb_ts]
        rgb_rel = str(rgb[rgb_ts][0])
        depth_rel = str(depth[depth_ts][0])
        tx, ty, tz, qx, qy, qz, qw = [float(value) for value in gt[gt_ts]]
        c2w = np.eye(4, dtype=np.float64)
        c2w[:3, :3] = quat_xyzw_to_rot(qx, qy, qz, qw)
        c2w[:3, 3] = [tx, ty, tz]
        frame_id = f"tum_{sequence}_{index:06d}"
        records.append(
            TumRecord(
                index=index,
                frame_id=frame_id,
                rgb_timestamp=float(rgb_ts),
                depth_timestamp=float(depth_ts),
                gt_timestamp=float(gt_ts),
                rgb_path=dataset_dir / rgb_rel,
                depth_path=dataset_dir / depth_rel,
                c2w_opencv=c2w,
                center=np.asarray([tx, ty, tz], dtype=np.float64),
                intrinsics=intrinsics,
            )
        )
    return records


def read_tum_file_list(path: Path, *, values_per_row: int | None = None) -> dict[float, list[str]]:
    rows: dict[float, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        timestamp = float(parts[0])
        values = parts[1:]
        if values_per_row is not None and len(values) < values_per_row:
            continue
        rows[timestamp] = values[:values_per_row] if values_per_row is not None else values
    return rows


def associate(first: dict[float, Any], second: dict[float, Any], *, max_difference: float) -> list[tuple[float, float]]:
    candidates = [
        (abs(a - b), a, b)
        for a in first
        for b in second
        if abs(a - b) < max_difference
    ]
    candidates.sort()
    first_used: set[float] = set()
    second_used: set[float] = set()
    matches = []
    for _, a, b in candidates:
        if a in first_used or b in second_used:
            continue
        first_used.add(a)
        second_used.add(b)
        matches.append((a, b))
    matches.sort()
    return matches


def quat_xyzw_to_rot(qx: float, qy: float, qz: float, qw: float) -> np.ndarray:
    q = np.asarray([qx, qy, qz, qw], dtype=np.float64)
    q /= max(float(np.linalg.norm(q)), 1e-12)
    x, y, z, w = q
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def da3_model_policy() -> dict[str, Any]:
    return {
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


def seed_window_manifest(frames: list[dict[str, Any]], model: dict[str, Any]) -> dict[str, Any]:
    frame_ids = [frame["id"] for frame in frames[:35]]
    return {
        "schemaVersion": "aether_da3_k_windows_v1",
        "sourceManifest": "photo_bundle.json",
        "sourceViewGraph": "view_graph.json",
        "model": model,
        "windowSize": 35,
        "windowingPolicy": {"kind": "tum_rgbd_seed_only_replaced_by_colmap_executor", "productionAllowed": False},
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
                "frameIDs": frame_ids,
                "uniqueFrameIDs": frame_ids,
                "coreFrameIDs": frame_ids,
                "bridgeFrameIDs": [],
                "frameCount": len(frame_ids),
                "uniqueFrameCount": len(frame_ids),
                "coreFrameCount": len(frame_ids),
                "bridgeFrameCount": 0,
                "inputHeight": 476,
                "inputWidth": 742,
            }
        ],
    }


def build_tum_pose_edges(records: list[TumRecord], centers: np.ndarray) -> list[dict[str, Any]]:
    edge_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    max_dist = max_pairwise_distance(centers)
    for i, record in enumerate(records):
        for j in range(i + 1, min(len(records), i + 41)):
            add_tum_edge(edge_by_pair, records, centers, i, j, max_dist, ["temporal_neighbor_proxy"])
    for i, center in enumerate(centers):
        dist = np.linalg.norm(centers - center[None, :], axis=1)
        nearest = [int(v) for v in np.argsort(dist)[1:25]]
        for j in nearest:
            if i < j:
                add_tum_edge(edge_by_pair, records, centers, i, j, max_dist, ["spatial_neighbor_proxy"])
            elif j < i:
                add_tum_edge(edge_by_pair, records, centers, j, i, max_dist, ["spatial_neighbor_proxy"])
    edges = list(edge_by_pair.values())
    edges.sort(key=lambda row: float(row["score"]), reverse=True)
    return edges


def add_tum_edge(
    edge_by_pair: dict[tuple[str, str], dict[str, Any]],
    records: list[TumRecord],
    centers: np.ndarray,
    i: int,
    j: int,
    max_dist: float,
    reasons: list[str],
) -> None:
    a = records[i]
    b = records[j]
    baseline = float(np.linalg.norm(centers[i] - centers[j]))
    temporal_gap = float(abs(b.rgb_timestamp - a.rgb_timestamp))
    orientation_gap = rotation_angle_degrees(a.c2w_opencv[:3, :3], b.c2w_opencv[:3, :3])
    baseline_score = max(0.0, 1.0 - baseline / max(max_dist, 1e-6))
    temporal_score = max(0.0, 1.0 - temporal_gap / 3.0)
    orientation_score = max(0.0, 1.0 - orientation_gap / 120.0)
    score = 0.45 * baseline_score + 0.35 * temporal_score + 0.20 * orientation_score
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
        "supportKind": "tum_rgbd_pose_proxy",
        "reasons": sorted(set((existing or {}).get("reasons", []) + reasons)),
    }


def rotation_angle_degrees(a: np.ndarray, b: np.ndarray) -> float:
    r = a.T @ b
    cos = float(np.clip((np.trace(r) - 1.0) * 0.5, -1.0, 1.0))
    return math.degrees(math.acos(cos))


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
        "16",
        "--temporal-neighbors",
        "8",
        "--max-image-size",
        "1000",
        "--max-num-features",
        "4096",
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
    plan = read_json(colmap_out / f"da3_k_windows_colmap_slots{actual_slots}.json")
    report = read_json(colmap_out / "colmap_view_graph_report.json")
    depth_index_path = da3_out / "depth_index.json"
    if not depth_index_path.exists():
        raise FileNotFoundError(depth_index_path)
    per_window = evaluate_per_window_pose(capture_dir, da3_out)
    stitched = evaluate_stitched_windows(capture_dir, da3_out, plan)
    official_streaming = evaluate_official_streaming_alignment(capture_dir, da3_out, plan)
    official_streaming_loop = evaluate_official_streaming_loop_alignment(capture_dir, da3_out, plan)
    depth_metrics = {} if skip_depth else evaluate_depth_gt(capture_dir, da3_out, max_depth_frames=max_depth_frames)
    metrics = {
        "schema_version": "aether_tum_rgbd_pose_depth_gt_metrics_v1",
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
    return metrics


def evaluate_per_window_pose(capture_dir: Path, da3_out: Path) -> dict[str, Any]:
    report = read_json(da3_out / "mac_da3_window_reports.json")
    rows = []
    for window in report.get("windows", []):
        local_by_frame = load_window_centers(window, da3_out)
        pred, gt, frame_ids = centers_against_gt(capture_dir, local_by_frame)
        if len(frame_ids) < 3:
            continue
        err, scale, _ = umeyama_align(pred, gt)
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
    report = read_json(da3_out / "mac_da3_window_reports.json")
    report_by_id = {str(window.get("windowID")): window for window in report.get("windows", [])}
    plan_windows = list(plan.get("windows", []))
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
    for window_id, mapped in global_by_window.items():
        for fid, center in mapped.items():
            selected_global.setdefault(fid, center)
            selected_source.setdefault(fid, window_id)

    pred, gt, frame_ids = centers_against_gt(capture_dir, selected_global)
    err, scale, aligned = umeyama_align(pred, gt)
    return {
        "frame_count": len(frame_ids),
        "pose_rmse": float(np.sqrt(np.mean(err * err))),
        "pose_median": float(np.median(err)),
        "pose_p90": float(np.percentile(err, 90)),
        "pose_p95": float(np.percentile(err, 95)),
        "pose_max": float(np.max(err)),
        "pose_sim3_scale": float(scale),
        "bridge_scale_mean": safe_mean([row.get("sim3_scale") for row in stitch_rows if "sim3_scale" in row]),
        "bridge_scale_std": safe_std([row.get("sim3_scale") for row in stitch_rows if "sim3_scale" in row]),
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


def evaluate_depth_gt(capture_dir: Path, da3_out: Path, *, max_depth_frames: int) -> dict[str, Any]:
    gt_manifest = read_json(capture_dir / "tum_rgbd_gt_manifest.json")
    gt_by_frame = {str(frame["frameID"]): frame for frame in gt_manifest.get("frames", [])}
    depth_index = read_json(da3_out / "depth_index.json")
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
        "per_frame_scale_mean": aggregate_depth_rows(per_frame),
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
        valid = np.isfinite(pred) & np.isfinite(gt) & (pred > 0.0) & (gt > 0.05) & (gt < 8.0)
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
    pred, gt = pair
    if pred.size == 0:
        return {"mapping": mapping, "scale": math.nan, "abs_rel": math.nan, "rmse_m": math.nan, "p90_abs_m": math.nan, "log_rmse": math.nan}
    scale = float(np.median(gt / np.maximum(pred, 1e-9)))
    aligned = pred * scale
    abs_err = np.abs(aligned - gt)
    log_err = np.log(np.maximum(aligned, 1e-6)) - np.log(np.maximum(gt, 1e-6))
    return {
        "mapping": mapping,
        "scale": scale,
        "abs_rel": float(np.mean(abs_err / np.maximum(gt, 1e-6))),
        "rmse_m": float(np.sqrt(np.mean(abs_err * abs_err))),
        "p90_abs_m": float(np.percentile(abs_err, 90)),
        "log_rmse": float(np.sqrt(np.mean(log_err * log_err))),
    }


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
        valid = np.isfinite(pred) & np.isfinite(gt) & (pred > 0.0) & (gt > 0.05) & (gt < 8.0)
        if int(valid.sum()) < 200:
            continue
        p = pred[valid].astype(np.float64)
        g = gt[valid].astype(np.float64)
        step = max(1, p.size // 2000)
        metrics = depth_metrics_from_pairs((p[::step], g[::step]), mapping="per_frame_inverse_depth" if inverse else "per_frame_depth")
        out.append({"frameID": frame_id, "windowID": row.get("windowID"), **metrics})
    return out


def aggregate_depth_rows(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {
        key: safe_mean([row.get(key) for row in rows])
        for key in ("abs_rel", "rmse_m", "p90_abs_m", "log_rmse")
    }


def load_gt_depth(path: Path, height: int, width: int) -> np.ndarray:
    raw = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(path)
    depth_m = raw.astype(np.float32) / 5000.0
    if depth_m.shape != (height, width):
        depth_m = cv2.resize(depth_m, (width, height), interpolation=cv2.INTER_NEAREST)
    return depth_m


def load_window_centers(window: dict[str, Any], da3_out: Path) -> dict[str, np.ndarray]:
    centers: dict[str, np.ndarray] = {}
    for frame in window.get("frames", []):
        frame_id = str(frame.get("frameID"))
        if frame_id in centers:
            continue
        pred_ext = np.fromfile(da3_out / str(frame["predExtrinsicsPath"]), dtype="<f4").reshape(3, 4)
        pred_w2c = np.eye(4, dtype=np.float64)
        pred_w2c[:3, :4] = pred_ext.astype(np.float64)
        centers[frame_id] = camera_center_from_w2c(pred_w2c)
    return centers


def evaluate_official_streaming_alignment(
    capture_dir: Path,
    da3_out: Path,
    plan: dict[str, Any],
    *,
    centers_against_gt_fn: Callable[[Path, dict[str, np.ndarray]], tuple[np.ndarray, np.ndarray, list[str]]] | None = None,
) -> dict[str, Any]:
    """Score DA3 official Streaming-style dense Sim3 alignment on exported windows.

    This intentionally mirrors the official DA3 Streaming alignment core:
    shared frames are converted to dense point maps from depth/intrinsics/extrinsics,
    confidence masks select reliable correspondences, and an IRLS weighted Sim3
    maps the later window into the previous/root coordinate system.  It does not
    run the official SALAD loop detector here because this GT driver already
    receives a fixed window graph; loop closure should be tested as a separate
    route when the official Python model runner is available.
    """

    if centers_against_gt_fn is None:
        centers_against_gt_fn = centers_against_gt

    report = read_json(da3_out / "mac_da3_window_reports.json")
    report_by_id = {str(window.get("windowID")): window for window in report.get("windows", [])}
    plan_windows = list(plan.get("windows", []))
    local_centers_by_window = {
        window_id: load_window_centers(report_by_id[window_id], da3_out)
        for window_id in report_by_id
    }
    rows_by_window = {
        window_id: {str(frame.get("frameID")): frame for frame in report_by_id[window_id].get("frames", [])}
        for window_id in report_by_id
    }

    identity = {"scale": 1.0, "rotation": np.eye(3), "translation": np.zeros(3)}
    transform_by_window: dict[str, dict[str, Any]] = {}
    global_centers_by_window: dict[str, dict[str, np.ndarray]] = {}
    stitch_rows: list[dict[str, Any]] = []

    for index, plan_window in enumerate(plan_windows):
        window_id = str(plan_window.get("id"))
        local = local_centers_by_window.get(window_id)
        if not local:
            continue
        if index == 0:
            transform_by_window[window_id] = identity
            global_centers_by_window[window_id] = {fid: center.copy() for fid, center in local.items()}
            stitch_rows.append(
                {
                    "windowID": window_id,
                    "status": "root",
                    "bridge_count": 0,
                    "alignMethod": "official_da3_streaming_dense_sim3",
                }
            )
            continue

        parent_id = str(plan_window.get("parentWindowID") or "")
        parent_global = global_centers_by_window.get(parent_id)
        parent_transform = transform_by_window.get(parent_id)
        if parent_global is None or parent_transform is None:
            parent_id = next((candidate for candidate in reversed(list(global_centers_by_window.keys()))), "")
            parent_global = global_centers_by_window.get(parent_id)
            parent_transform = transform_by_window.get(parent_id)

        bridge_ids = [str(fid) for fid in plan_window.get("bridgeFrameIDs", [])]
        current_rows = rows_by_window.get(window_id, {})
        parent_rows = rows_by_window.get(parent_id, {})
        shared = [fid for fid in bridge_ids if fid in current_rows and fid in parent_rows]
        if len(shared) < 1:
            shared = [fid for fid in current_rows if fid in parent_rows]

        if not parent_global or parent_transform is None or len(shared) < 1:
            transform_by_window[window_id] = identity
            global_centers_by_window[window_id] = {fid: center.copy() for fid, center in local.items()}
            stitch_rows.append(
                {
                    "windowID": window_id,
                    "status": "failed_insufficient_shared_frames",
                    "parentWindowID": parent_id,
                    "bridge_count": len(shared),
                    "alignMethod": "official_da3_streaming_dense_sim3",
                }
            )
            continue

        try:
            transform, edge = estimate_official_dense_sim3(
                da3_out=da3_out,
                parent_rows=parent_rows,
                current_rows=current_rows,
                parent_transform=parent_transform,
                shared_frame_ids=shared,
            )
        except Exception as exc:  # Keep the benchmark alive and make the failure visible.
            transform = identity
            edge = {
                "status": "failed_dense_sim3",
                "error": f"{type(exc).__name__}: {exc}",
                "point_count": 0,
                "bridge_rmse": math.nan,
                "bridge_p90": math.nan,
                "sim3_scale": math.nan,
            }

        mapped = {fid: apply_sim3(center[None, :], transform)[0] for fid, center in local.items()}
        transform_by_window[window_id] = transform
        global_centers_by_window[window_id] = mapped
        stitch_rows.append(
            {
                "windowID": window_id,
                "parentWindowID": parent_id,
                "bridge_count": len(shared),
                "alignMethod": "official_da3_streaming_dense_sim3",
                **edge,
            }
        )

    selected_global: dict[str, np.ndarray] = {}
    selected_source: dict[str, str] = {}
    for plan_window in plan_windows:
        window_id = str(plan_window.get("id"))
        mapped = global_centers_by_window.get(window_id, {})
        for fid in [str(value) for value in plan_window.get("coreFrameIDs", [])]:
            if fid in mapped and fid not in selected_global:
                selected_global[fid] = mapped[fid]
                selected_source[fid] = window_id
    for window_id, mapped in global_centers_by_window.items():
        for fid, center in mapped.items():
            selected_global.setdefault(fid, center)
            selected_source.setdefault(fid, window_id)

    pred, gt, frame_ids = centers_against_gt_fn(capture_dir, selected_global)
    err, scale, aligned = umeyama_align(pred, gt)
    return {
        "schema_version": "aether_official_da3_streaming_alignment_metrics_v1",
        "note": "Official DA3 Streaming-style dense Sim3 over existing exported windows; SALAD loop closure is not included in this route.",
        "frame_count": len(frame_ids),
        "pose_rmse": float(np.sqrt(np.mean(err * err))),
        "pose_median": float(np.median(err)),
        "pose_p90": float(np.percentile(err, 90)),
        "pose_p95": float(np.percentile(err, 95)),
        "pose_max": float(np.max(err)),
        "pose_sim3_scale": float(scale),
        "bridge_scale_mean": safe_mean([row.get("sim3_scale") for row in stitch_rows if "sim3_scale" in row]),
        "bridge_scale_std": safe_std([row.get("sim3_scale") for row in stitch_rows if "sim3_scale" in row]),
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


def evaluate_official_streaming_loop_alignment(
    capture_dir: Path,
    da3_out: Path,
    plan: dict[str, Any],
    *,
    centers_against_gt_fn: Callable[[Path, dict[str, np.ndarray]], tuple[np.ndarray, np.ndarray, list[str]]] | None = None,
) -> dict[str, Any]:
    """Run official DA3 Streaming-style dense Sim3 plus Sim3LoopOptimizer.

    This route uses the official optimizer implementation vendored under
    tools/vendor/official_da3_streaming. Loop candidates come from the same
    verified view-graph plan used by this benchmark. Candidates without shared
    frames require the official extra loop-chunk DA3 forward pass, so this route
    reports and skips them instead of faking a constraint.
    """

    if centers_against_gt_fn is None:
        centers_against_gt_fn = centers_against_gt

    report = read_json(da3_out / "mac_da3_window_reports.json")
    report_by_id = {str(window.get("windowID")): window for window in report.get("windows", [])}
    plan_windows = list(plan.get("windows", []))
    window_ids = [str(window.get("id")) for window in plan_windows]
    window_index = {window_id: idx for idx, window_id in enumerate(window_ids)}
    rows_by_window = {
        window_id: {str(frame.get("frameID")): frame for frame in report_by_id[window_id].get("frames", [])}
        for window_id in report_by_id
    }
    centers_by_window = {
        window_id: load_window_centers(report_by_id[window_id], da3_out)
        for window_id in report_by_id
    }

    identity = {"scale": 1.0, "rotation": np.eye(3), "translation": np.zeros(3)}
    sequential_transforms: list[tuple[float, np.ndarray, np.ndarray]] = []
    tree_edges: list[dict[str, Any]] = []
    chain_compatible = True

    for index in range(1, len(plan_windows)):
        plan_window = plan_windows[index]
        window_id = str(plan_window.get("id"))
        expected_parent_id = window_ids[index - 1]
        parent_id = str(plan_window.get("parentWindowID") or expected_parent_id)
        if parent_id != expected_parent_id:
            chain_compatible = False
            parent_id = expected_parent_id
        bridge_ids = [str(fid) for fid in plan_window.get("bridgeFrameIDs", [])]
        current_rows = rows_by_window.get(window_id, {})
        parent_rows = rows_by_window.get(parent_id, {})
        shared = [fid for fid in bridge_ids if fid in current_rows and fid in parent_rows]
        if len(shared) < 1:
            shared = [fid for fid in current_rows if fid in parent_rows]
        if len(shared) < 1:
            sequential_transforms.append(transform_to_tuple(identity))
            tree_edges.append(
                {
                    "sourceWindowID": window_id,
                    "targetWindowID": parent_id,
                    "status": "failed_insufficient_shared_frames",
                    "sharedFrameCount": len(shared),
                    "sim3_scale": math.nan,
                }
            )
            continue

        try:
            transform, edge = estimate_official_dense_sim3_raw(
                da3_out=da3_out,
                target_rows=parent_rows,
                source_rows=current_rows,
                shared_frame_ids=shared,
            )
        except Exception as exc:
            transform = identity
            edge = {
                "status": "failed_dense_sim3",
                "error": f"{type(exc).__name__}: {exc}",
                "point_count": 0,
                "bridge_rmse": math.nan,
                "bridge_p90": math.nan,
                "sim3_scale": math.nan,
            }

        sequential_transforms.append(transform_to_tuple(transform))
        tree_edges.append(
            {
                "sourceWindowID": window_id,
                "targetWindowID": parent_id,
                "sharedFrameCount": len(shared),
                "alignMethod": "official_da3_streaming_dense_sim3_raw_tree",
                **edge,
            }
        )

    loop_constraints: list[tuple[int, int, tuple[float, np.ndarray, np.ndarray]]] = []
    loop_edges: list[dict[str, Any]] = []
    skipped_without_shared = 0
    skipped_adjacent = 0
    skipped_quality_gate = 0
    min_loop_shared_frames = 3
    max_loop_bridge_p90 = 0.15

    for candidate in plan.get("loopCandidates", []):
        source_id = str(candidate.get("sourceWindowID"))
        target_id = str(candidate.get("targetWindowID"))
        if source_id not in window_index or target_id not in window_index:
            continue
        source_idx = window_index[source_id]
        target_idx = window_index[target_id]
        if abs(source_idx - target_idx) <= 1:
            skipped_adjacent += 1
            continue
        later_id, earlier_id = (source_id, target_id) if source_idx > target_idx else (target_id, source_id)
        later_idx, earlier_idx = window_index[later_id], window_index[earlier_id]
        later_rows = rows_by_window.get(later_id, {})
        earlier_rows = rows_by_window.get(earlier_id, {})
        shared = [str(fid) for fid in candidate.get("sharedFrameIDs", []) if str(fid) in later_rows and str(fid) in earlier_rows]
        if len(shared) < 1:
            skipped_without_shared += 1
            continue
        if len(shared) < min_loop_shared_frames:
            skipped_quality_gate += 1
            loop_edges.append(
                {
                    "sourceWindowID": later_id,
                    "targetWindowID": earlier_id,
                    "sourceWindowIndex": later_idx,
                    "targetWindowIndex": earlier_idx,
                    "sharedFrameCount": len(shared),
                    "status": "skipped_quality_gate",
                    "reason": f"sharedFrameCount < {min_loop_shared_frames}",
                }
            )
            continue
        try:
            transform, edge = estimate_official_dense_sim3_raw(
                da3_out=da3_out,
                target_rows=earlier_rows,
                source_rows=later_rows,
                shared_frame_ids=shared,
            )
        except Exception as exc:
            loop_edges.append(
                {
                    "sourceWindowID": later_id,
                    "targetWindowID": earlier_id,
                    "sourceWindowIndex": later_idx,
                    "targetWindowIndex": earlier_idx,
                    "sharedFrameCount": len(shared),
                    "status": "failed_dense_sim3",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            continue
        if float(edge.get("bridge_p90", math.inf)) > max_loop_bridge_p90:
            skipped_quality_gate += 1
            loop_edges.append(
                {
                    "sourceWindowID": later_id,
                    "targetWindowID": earlier_id,
                    "sourceWindowIndex": later_idx,
                    "targetWindowIndex": earlier_idx,
                    "sharedFrameCount": len(shared),
                    "alignMethod": "official_da3_streaming_dense_sim3_loop_constraint",
                    **edge,
                    "status": "skipped_quality_gate",
                    "reason": f"bridge_p90 > {max_loop_bridge_p90}",
                }
            )
            continue
        loop_constraints.append((later_idx, earlier_idx, transform_to_tuple(transform)))
        loop_edges.append(
            {
                "sourceWindowID": later_id,
                "targetWindowID": earlier_id,
                "sourceWindowIndex": later_idx,
                "targetWindowIndex": earlier_idx,
                "sharedFrameCount": len(shared),
                "alignMethod": "official_da3_streaming_dense_sim3_loop_constraint",
                **edge,
            }
        )

    pre_loop_score = score_official_window_transforms(
        capture_dir=capture_dir,
        plan_windows=plan_windows,
        window_ids=window_ids,
        centers_by_window=centers_by_window,
        transforms=sequential_transforms,
        centers_against_gt_fn=centers_against_gt_fn,
    )

    optimized_transforms = sequential_transforms
    optimizer_status = "not_run_no_loop_constraints"
    optimizer_error = None
    if loop_constraints and len(sequential_transforms) == max(len(plan_windows) - 1, 0):
        try:
            optimized_transforms = run_official_sim3_loop_optimizer(sequential_transforms, loop_constraints)
            optimizer_status = "optimized"
        except Exception as exc:
            optimizer_status = "failed"
            optimizer_error = f"{type(exc).__name__}: {exc}"

    score = score_official_window_transforms(
        capture_dir=capture_dir,
        plan_windows=plan_windows,
        window_ids=window_ids,
        centers_by_window=centers_by_window,
        transforms=optimized_transforms,
        centers_against_gt_fn=centers_against_gt_fn,
    )
    return {
        "schema_version": "aether_official_da3_streaming_loop_alignment_metrics_v1",
        "note": "Official DA3 Streaming-style dense Sim3 tree plus official Sim3LoopOptimizer. Loop constraints come from benchmark view-graph candidates with shared frames; non-shared loop chunks require extra DA3 forward passes and are reported as skipped.",
        "status": optimizer_status,
        "optimizer_error": optimizer_error,
        "chain_compatible": chain_compatible,
        "frame_count": score["frame_count"],
        "pose_rmse": score["pose_rmse"],
        "pose_median": score["pose_median"],
        "pose_p90": score["pose_p90"],
        "pose_p95": score["pose_p95"],
        "pose_max": score["pose_max"],
        "pose_sim3_scale": score["pose_sim3_scale"],
        "pre_loop_pose_rmse": pre_loop_score["pose_rmse"],
        "pre_loop_pose_p90": pre_loop_score["pose_p90"],
        "loop_delta_rmse": score["pose_rmse"] - pre_loop_score["pose_rmse"],
        "loop_delta_p90": score["pose_p90"] - pre_loop_score["pose_p90"],
        "tree_edge_count": len(tree_edges),
        "loop_constraint_count": len(loop_constraints),
        "loop_candidate_count": len(plan.get("loopCandidates", [])),
        "loop_skipped_without_shared_frames": skipped_without_shared,
        "loop_skipped_adjacent_windows": skipped_adjacent,
        "loop_skipped_quality_gate": skipped_quality_gate,
        "loop_min_shared_frames": min_loop_shared_frames,
        "loop_max_bridge_p90": max_loop_bridge_p90,
        "tree_bridge_scale_mean": safe_mean([row.get("sim3_scale") for row in tree_edges if "sim3_scale" in row]),
        "tree_bridge_scale_std": safe_std([row.get("sim3_scale") for row in tree_edges if "sim3_scale" in row]),
        "loop_bridge_scale_mean": safe_mean([row.get("sim3_scale") for row in loop_edges if "sim3_scale" in row]),
        "loop_bridge_scale_std": safe_std([row.get("sim3_scale") for row in loop_edges if "sim3_scale" in row]),
        "tree_edges": tree_edges,
        "loop_edges": loop_edges,
        "selected_order_frame_ids": score["selected_order_frame_ids"],
        "selected_order_window_ids": score["selected_order_window_ids"],
        "selected_order_errors": score["selected_order_errors"],
        "trajectory": score["trajectory"],
    }


def score_official_window_transforms(
    *,
    capture_dir: Path,
    plan_windows: list[dict[str, Any]],
    window_ids: list[str],
    centers_by_window: dict[str, dict[str, np.ndarray]],
    transforms: list[tuple[float, np.ndarray, np.ndarray]],
    centers_against_gt_fn: Callable[[Path, dict[str, np.ndarray]], tuple[np.ndarray, np.ndarray, list[str]]],
) -> dict[str, Any]:
    identity = {"scale": 1.0, "rotation": np.eye(3), "translation": np.zeros(3)}
    cumulative = accumulate_sim3_official(transforms)
    global_transform_by_window: dict[str, dict[str, Any]] = {window_ids[0]: identity} if window_ids else {}
    for index, transform in enumerate(cumulative, start=1):
        if index < len(window_ids):
            global_transform_by_window[window_ids[index]] = tuple_to_transform(transform)

    selected_global: dict[str, np.ndarray] = {}
    selected_source: dict[str, str] = {}
    for plan_window in plan_windows:
        window_id = str(plan_window.get("id"))
        transform = global_transform_by_window.get(window_id, identity)
        centers = centers_by_window.get(window_id, {})
        for fid in [str(value) for value in plan_window.get("coreFrameIDs", [])]:
            if fid in centers and fid not in selected_global:
                selected_global[fid] = apply_sim3(centers[fid][None, :], transform)[0]
                selected_source[fid] = window_id
    for window_id, centers in centers_by_window.items():
        transform = global_transform_by_window.get(window_id, identity)
        for fid, center in centers.items():
            if fid not in selected_global:
                selected_global[fid] = apply_sim3(center[None, :], transform)[0]
                selected_source[fid] = window_id

    pred, gt, frame_ids = centers_against_gt_fn(capture_dir, selected_global)
    err, scale, aligned = umeyama_align(pred, gt)
    return {
        "frame_count": len(frame_ids),
        "pose_rmse": float(np.sqrt(np.mean(err * err))),
        "pose_median": float(np.median(err)),
        "pose_p90": float(np.percentile(err, 90)),
        "pose_p95": float(np.percentile(err, 95)),
        "pose_max": float(np.max(err)),
        "pose_sim3_scale": float(scale),
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


def run_official_sim3_loop_optimizer(
    sequential_transforms: list[tuple[float, np.ndarray, np.ndarray]],
    loop_constraints: list[tuple[int, int, tuple[float, np.ndarray, np.ndarray]]],
) -> list[tuple[float, np.ndarray, np.ndarray]]:
    if str(OFFICIAL_DA3_STREAMING_VENDOR) not in sys.path:
        sys.path.insert(0, str(OFFICIAL_DA3_STREAMING_VENDOR))
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
    return Sim3LoopOptimizer(config).optimize(sequential_transforms, loop_constraints)


def estimate_official_dense_sim3_raw(
    *,
    da3_out: Path,
    target_rows: dict[str, dict[str, Any]],
    source_rows: dict[str, dict[str, Any]],
    shared_frame_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_points = []
    target_points = []
    weights = []
    per_frame_counts: dict[str, int] = {}
    median_confs: list[float] = []
    payloads: list[tuple[str, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []

    for frame_id in shared_frame_ids:
        target_point_map, target_conf = load_point_map_and_conf(target_rows[frame_id], da3_out)
        source_point_map, source_conf = load_point_map_and_conf(source_rows[frame_id], da3_out)
        payloads.append((frame_id, target_point_map, target_conf, source_point_map, source_conf))
        median_confs.extend([float(np.median(target_conf)), float(np.median(source_conf))])

    conf_threshold = min(median_confs) * 0.1 if median_confs else 0.0
    for frame_id, target_point_map, target_conf, source_point_map, source_conf in payloads:
        mask = (
            np.isfinite(target_point_map).all(axis=2)
            & np.isfinite(source_point_map).all(axis=2)
            & np.isfinite(target_conf)
            & np.isfinite(source_conf)
            & (target_conf > conf_threshold)
            & (source_conf > conf_threshold)
        )
        count = int(np.count_nonzero(mask))
        per_frame_counts[frame_id] = count
        if count == 0:
            continue
        target_points.append(target_point_map[mask])
        source_points.append(source_point_map[mask])
        weights.append(np.sqrt(target_conf[mask].astype(np.float64) * source_conf[mask].astype(np.float64)))

    if not source_points:
        raise ValueError("No dense correspondences survived the confidence mask")

    src = np.concatenate(source_points, axis=0).astype(np.float64)
    dst = np.concatenate(target_points, axis=0).astype(np.float64)
    w = np.concatenate(weights, axis=0).astype(np.float64)
    transform = robust_weighted_sim3_official(src, dst, w, delta=0.1, max_iters=5, tol=1e-9)
    residual = np.linalg.norm(apply_sim3(src, transform) - dst, axis=1)
    return transform, {
        "status": "stitched",
        "point_count": int(src.shape[0]),
        "per_frame_point_count": per_frame_counts,
        "confidence_threshold": float(conf_threshold),
        "bridge_rmse": float(np.sqrt(np.mean(residual * residual))),
        "bridge_p90": float(np.percentile(residual, 90)),
        "sim3_scale": float(transform["scale"]),
    }


def transform_to_tuple(transform: dict[str, Any]) -> tuple[float, np.ndarray, np.ndarray]:
    return (
        float(transform["scale"]),
        np.asarray(transform["rotation"], dtype=np.float64),
        np.asarray(transform["translation"], dtype=np.float64),
    )


def tuple_to_transform(transform: tuple[float, np.ndarray, np.ndarray]) -> dict[str, Any]:
    scale, rotation, translation = transform
    return {
        "scale": float(scale),
        "rotation": np.asarray(rotation, dtype=np.float64),
        "translation": np.asarray(translation, dtype=np.float64),
    }


def accumulate_sim3_official(
    transforms: list[tuple[float, np.ndarray, np.ndarray]]
) -> list[tuple[float, np.ndarray, np.ndarray]]:
    if not transforms:
        return []
    cumulative = [transforms[0]]
    for transform in transforms[1:]:
        s_prev, r_prev, t_prev = cumulative[-1]
        s_next, r_next, t_next = transform
        s_cum = float(s_prev) * float(s_next)
        r_cum = np.asarray(r_prev) @ np.asarray(r_next)
        t_cum = float(s_prev) * (np.asarray(r_prev) @ np.asarray(t_next)) + np.asarray(t_prev)
        cumulative.append((s_cum, r_cum, t_cum))
    return cumulative


def estimate_official_dense_sim3(
    *,
    da3_out: Path,
    parent_rows: dict[str, dict[str, Any]],
    current_rows: dict[str, dict[str, Any]],
    parent_transform: dict[str, Any],
    shared_frame_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_points = []
    target_points = []
    weights = []
    per_frame_counts: dict[str, int] = {}
    median_confs: list[float] = []
    payloads: list[tuple[str, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []

    for frame_id in shared_frame_ids:
        parent_point_map, parent_conf = load_point_map_and_conf(parent_rows[frame_id], da3_out)
        current_point_map, current_conf = load_point_map_and_conf(current_rows[frame_id], da3_out)
        parent_point_map = apply_sim3(parent_point_map.reshape(-1, 3), parent_transform).reshape(parent_point_map.shape)
        payloads.append((frame_id, parent_point_map, parent_conf, current_point_map, current_conf))
        median_confs.extend([float(np.median(parent_conf)), float(np.median(current_conf))])

    conf_threshold = min(median_confs) * 0.1 if median_confs else 0.0
    for frame_id, parent_point_map, parent_conf, current_point_map, current_conf in payloads:
        mask = (
            np.isfinite(parent_point_map).all(axis=2)
            & np.isfinite(current_point_map).all(axis=2)
            & np.isfinite(parent_conf)
            & np.isfinite(current_conf)
            & (parent_conf > conf_threshold)
            & (current_conf > conf_threshold)
        )
        count = int(np.count_nonzero(mask))
        per_frame_counts[frame_id] = count
        if count == 0:
            continue
        target_points.append(parent_point_map[mask])
        source_points.append(current_point_map[mask])
        weights.append(np.sqrt(parent_conf[mask].astype(np.float64) * current_conf[mask].astype(np.float64)))

    if not source_points:
        raise ValueError("No dense correspondences survived the confidence mask")

    src = np.concatenate(source_points, axis=0).astype(np.float64)
    dst = np.concatenate(target_points, axis=0).astype(np.float64)
    w = np.concatenate(weights, axis=0).astype(np.float64)
    transform = robust_weighted_sim3_official(src, dst, w, delta=0.1, max_iters=5, tol=1e-9)
    residual = np.linalg.norm(apply_sim3(src, transform) - dst, axis=1)
    return transform, {
        "status": "stitched",
        "point_count": int(src.shape[0]),
        "per_frame_point_count": per_frame_counts,
        "confidence_threshold": float(conf_threshold),
        "bridge_rmse": float(np.sqrt(np.mean(residual * residual))),
        "bridge_p90": float(np.percentile(residual, 90)),
        "sim3_scale": float(transform["scale"]),
    }


def load_point_map_and_conf(frame: dict[str, Any], da3_out: Path) -> tuple[np.ndarray, np.ndarray]:
    height = int(frame["depthHeight"])
    width = int(frame["depthWidth"])
    depth = np.fromfile(da3_out / str(frame["relativeDepthPath"]), dtype="<f4").reshape(height, width)
    conf = np.fromfile(da3_out / str(frame["confidencePath"]), dtype="<f4").reshape(height, width)
    intrinsics = np.fromfile(da3_out / str(frame["predIntrinsicsPath"]), dtype="<f4").reshape(3, 3)
    extrinsics = np.fromfile(da3_out / str(frame["predExtrinsicsPath"]), dtype="<f4").reshape(3, 4)
    return depth_to_point_map_official(depth, intrinsics, extrinsics), conf


def depth_to_point_map_official(depth: np.ndarray, intrinsics: np.ndarray, extrinsics: np.ndarray) -> np.ndarray:
    height, width = depth.shape
    u, v = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    pixels = np.stack([u, v, np.ones_like(u)], axis=-1).reshape(-1, 3)
    rays = pixels @ np.linalg.inv(intrinsics.astype(np.float64)).T
    camera_points = rays * depth.reshape(-1, 1).astype(np.float64)
    camera_points_h = np.concatenate([camera_points, np.ones((camera_points.shape[0], 1))], axis=1)
    w2c = np.eye(4, dtype=np.float64)
    w2c[:3, :4] = extrinsics.astype(np.float64)
    c2w = np.linalg.inv(w2c)
    world_points = camera_points_h @ c2w.T
    return world_points[:, :3].reshape(height, width, 3)


def robust_weighted_sim3_official(
    src: np.ndarray,
    dst: np.ndarray,
    weights: np.ndarray,
    *,
    delta: float,
    max_iters: int,
    tol: float,
) -> dict[str, Any]:
    weights = np.asarray(weights, dtype=np.float64)
    weights = weights / max(float(np.sum(weights)), 1e-12)
    transform = weighted_sim3_official(src, dst, weights)
    previous_error = float("inf")
    for _ in range(max_iters):
        residual = np.linalg.norm(apply_sim3(src, transform) - dst, axis=1)
        huber = np.ones_like(residual)
        large = residual > delta
        huber[large] = delta / np.maximum(residual[large], 1e-12)
        combined = weights * huber
        combined = combined / max(float(np.sum(combined)), 1e-12)
        updated = weighted_sim3_official(src, dst, combined)
        param_change = abs(float(updated["scale"]) - float(transform["scale"])) + float(
            np.linalg.norm(np.asarray(updated["translation"]) - np.asarray(transform["translation"]))
        )
        rot_delta = np.asarray(updated["rotation"]) @ np.asarray(transform["rotation"]).T
        rot_angle = math.acos(min(1.0, max(-1.0, (float(np.trace(rot_delta)) - 1.0) / 2.0)))
        current_error = float(np.sum(huber_loss_official(residual, delta) * weights))
        transform = updated
        if (param_change < tol and rot_angle < math.radians(0.1)) or (
            previous_error < float("inf") and abs(previous_error - current_error) < tol * max(previous_error, 1e-12)
        ):
            break
        previous_error = current_error
    return transform


def weighted_sim3_official(src: np.ndarray, dst: np.ndarray, weights: np.ndarray) -> dict[str, Any]:
    total = float(np.sum(weights))
    if total < 1e-12:
        raise ValueError("Total weight too small for dense Sim3")
    normalized = weights / total
    mu_src = np.sum(normalized[:, None] * src, axis=0)
    mu_dst = np.sum(normalized[:, None] * dst, axis=0)
    src_centered = src - mu_src
    dst_centered = dst - mu_dst
    scale_src = math.sqrt(float(np.sum(normalized * np.sum(src_centered * src_centered, axis=1))))
    scale_dst = math.sqrt(float(np.sum(normalized * np.sum(dst_centered * dst_centered, axis=1))))
    scale = scale_dst / max(scale_src, 1e-12)
    weighted_src = (scale * src_centered) * np.sqrt(normalized)[:, None]
    weighted_dst = dst_centered * np.sqrt(normalized)[:, None]
    h = weighted_src.T @ weighted_dst
    u, _, vt = np.linalg.svd(h)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[2, :] *= -1
        rotation = vt.T @ u.T
    translation = mu_dst - scale * (rotation @ mu_src)
    return {"scale": float(scale), "rotation": rotation, "translation": translation}


def huber_loss_official(residual: np.ndarray, delta: float) -> np.ndarray:
    abs_residual = np.abs(residual)
    return np.where(abs_residual <= delta, 0.5 * residual * residual, delta * (abs_residual - 0.5 * delta))


def centers_against_gt(capture_dir: Path, pred_by_frame: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    gt_manifest = read_json(capture_dir / "tum_rgbd_gt_manifest.json")
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
    return np.stack(pred, axis=0), np.stack(gt, axis=0), kept


def camera_center_from_w2c(w2c: np.ndarray) -> np.ndarray:
    r = w2c[:3, :3].astype(np.float64)
    t = w2c[:3, 3].astype(np.float64)
    return (-r.T @ t).astype(np.float64)


def opencv_c2w_to_arkit_c2w(c2w_opencv: np.ndarray) -> np.ndarray:
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


def umeyama_align(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, float, np.ndarray]:
    transform = estimate_sim3(src, dst)
    aligned = apply_sim3(src.astype(np.float64), transform)
    err = np.linalg.norm(aligned - dst.astype(np.float64), axis=1)
    return err, float(transform["scale"]), aligned


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


def aggregate(sequence_results: list[dict[str, Any]]) -> dict[str, Any]:
    routes = [route for seq in sequence_results for route in seq.get("routes", [])]
    if not routes:
        return {}
    all_pose = np.asarray([err for route in routes for err in route["stitched"].get("selected_order_errors", [])], dtype=np.float64)
    return {
        "sequence_count": len(sequence_results),
        "route_count": len(routes),
        "pose_rmse_all_routes": float(np.sqrt(np.mean(all_pose * all_pose))) if all_pose.size else math.nan,
        "pose_p90_all_routes": float(np.percentile(all_pose, 90)) if all_pose.size else math.nan,
    }


def write_sequence_summary(path: Path, sequence_result: dict[str, Any]) -> None:
    lines = [
        f"# TUM RGB-D {sequence_result['sequence']} DA3 GT",
        "",
        "| route | windows | selected | dropped | local RMSE | bridge RMSE | bridge P90 | dense Sim3 RMSE | dense Sim3 P90 | dense+loop RMSE | dense+loop P90 | loop constraints | depth AbsRel | depth P90 m |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for route in sequence_result.get("routes", []):
        depth = route.get("depth", {}).get("global_scale", {})
        lines.append(
            "| slots{actual_slots} | {window_count} | {selected_frame_count} | {dropped_frame_count} | "
            "{local:.6f} | {pose_rmse:.6f} | {pose_p90:.6f} | {official_rmse:.6f} | {official_p90:.6f} | {loop_rmse:.6f} | {loop_p90:.6f} | {loop_constraints} | {abs_rel:.6f} | {p90_abs:.6f} |".format(
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
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_overall_summary(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# TUM RGB-D DA3 Multi-Window GT Benchmark",
        "",
        f"- route: {summary['route']}",
        f"- sequences: {', '.join(summary['sequences'])}",
        f"- bridge overlap: {summary['bridge_overlap']}",
        "",
        "| sequence | route | windows | selected | dropped | local RMSE | bridge RMSE | bridge P90 | dense Sim3 RMSE | dense Sim3 P90 | dense+loop RMSE | dense+loop P90 | loop constraints | depth AbsRel | depth P90 m |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for seq in summary.get("results", []):
        for route in seq.get("routes", []):
            depth = route.get("depth", {}).get("global_scale", {})
            lines.append(
                "| {sequence} | slots{actual_slots} | {window_count} | {selected_frame_count} | {dropped_frame_count} | "
                "{local:.6f} | {pose_rmse:.6f} | {pose_p90:.6f} | {official_rmse:.6f} | {official_p90:.6f} | {loop_rmse:.6f} | {loop_p90:.6f} | {loop_constraints} | {abs_rel:.6f} | {p90_abs:.6f} |".format(
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
    draw_grouped_bar_chart(
        chart_dir / "pose_rmse_p90.png",
        title="TUM RGB-D pose GT",
        labels=labels,
        series=[
            ("local RMSE", [row[1]["per_window"].get("mean_window_rmse", math.nan) for row in rows], (67, 116, 179)),
            ("stitched RMSE", [row[1].get("pose_rmse", math.nan) for row in rows], (213, 94, 0)),
            ("stitched P90", [row[1].get("pose_p90", math.nan) for row in rows], (45, 45, 45)),
        ],
        y_label="camera center error after Sim3",
    )
    draw_grouped_bar_chart(
        chart_dir / "depth_absrel_p90.png",
        title="TUM RGB-D depth GT",
        labels=labels,
        series=[
            ("AbsRel", [row[1].get("depth", {}).get("global_scale", {}).get("abs_rel", math.nan) for row in rows], (0, 158, 115)),
            ("P90 abs m", [row[1].get("depth", {}).get("global_scale", {}).get("p90_abs_m", math.nan) for row in rows], (204, 121, 167)),
        ],
        y_label="depth GT metric",
    )

    first_route = rows[0][1]
    trajectory = first_route.get("stitched", {}).get("trajectory", [])
    if trajectory:
        gt = np.asarray([row["gt"] for row in trajectory], dtype=np.float64)
        pred = np.asarray([row["predAligned"] for row in trajectory], dtype=np.float64)
        draw_trajectory_chart(chart_dir / "trajectory_topdown.png", gt, pred)


def draw_grouped_bar_chart(
    path: Path,
    *,
    title: str,
    labels: list[str],
    series: list[tuple[str, list[float], tuple[int, int, int]]],
    y_label: str,
) -> None:
    width = max(1000, 260 + len(labels) * 190)
    height = 620
    margin_l, margin_r, margin_t, margin_b = 110, 40, 80, 150
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = default_font(20)
    small = default_font(16)
    title_font = default_font(28)
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    all_values = [float(v) for _, values, _ in series for v in values if math.isfinite(float(v))]
    ymax = max(all_values + [1.0]) * 1.18
    draw.text((margin_l, 24), title, fill=(20, 20, 20), font=title_font)
    draw.text((margin_l, 56), y_label, fill=(80, 80, 80), font=small)
    for i in range(6):
        y = margin_t + plot_h - int(plot_h * i / 5)
        value = ymax * i / 5
        draw.line((margin_l, y, width - margin_r, y), fill=(230, 230, 230))
        draw.text((18, y - 10), f"{value:.2f}", fill=(90, 90, 90), font=small)
    group_w = plot_w / max(len(labels), 1)
    bar_w = max(14, int(group_w / (len(series) + 1.4)))
    for i, label in enumerate(labels):
        center = margin_l + group_w * (i + 0.5)
        base_x = center - (len(series) * bar_w) / 2
        for s_idx, (_, values, color) in enumerate(series):
            value = float(values[i])
            if not math.isfinite(value):
                continue
            bar_h = int(plot_h * value / ymax)
            x0 = int(base_x + s_idx * bar_w)
            x1 = int(x0 + bar_w - 4)
            y0 = margin_t + plot_h - bar_h
            y1 = margin_t + plot_h
            draw.rectangle((x0, y0, x1, y1), fill=color)
            draw.text((x0, y0 - 20), f"{value:.2f}", fill=color, font=small)
        label_lines = wrap_label(label, 18)
        for line_i, line in enumerate(label_lines[:3]):
            draw.text((int(center - 78), margin_t + plot_h + 16 + line_i * 19), line, fill=(40, 40, 40), font=small)
    legend_x = margin_l
    legend_y = height - 42
    for name, _, color in series:
        draw.rectangle((legend_x, legend_y, legend_x + 18, legend_y + 18), fill=color)
        draw.text((legend_x + 26, legend_y - 1), name, fill=(40, 40, 40), font=small)
        legend_x += 180
    image.save(path)


def draw_trajectory_chart(path: Path, gt: np.ndarray, pred: np.ndarray) -> None:
    width = height = 760
    margin = 70
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    small = default_font(16)
    title_font = default_font(26)
    xy = np.concatenate([gt[:, [0, 2]], pred[:, [0, 2]]], axis=0)
    lo = xy.min(axis=0)
    hi = xy.max(axis=0)
    center = (lo + hi) * 0.5
    span = max(float(np.max(hi - lo)), 1e-6) * 1.12

    def project(points: np.ndarray) -> list[tuple[int, int]]:
        norm = (points[:, [0, 2]] - center[None, :]) / span + 0.5
        xs = margin + norm[:, 0] * (width - 2 * margin)
        ys = height - margin - norm[:, 1] * (height - 2 * margin)
        return [(int(x), int(y)) for x, y in zip(xs, ys)]

    draw.text((margin, 22), "Trajectory top-down", fill=(20, 20, 20), font=title_font)
    draw.rectangle((margin, margin, width - margin, height - margin), outline=(220, 220, 220))
    gt_pts = project(gt)
    pred_pts = project(pred)
    if len(gt_pts) > 1:
        draw.line(gt_pts, fill=(67, 116, 179), width=4)
    if len(pred_pts) > 1:
        draw.line(pred_pts, fill=(213, 94, 0), width=3)
    draw.rectangle((margin, height - 42, margin + 18, height - 24), fill=(67, 116, 179))
    draw.text((margin + 26, height - 44), "GT", fill=(40, 40, 40), font=small)
    draw.rectangle((margin + 95, height - 42, margin + 113, height - 24), fill=(213, 94, 0))
    draw.text((margin + 121, height - 44), "DA3 stitched aligned", fill=(40, 40, 40), font=small)
    image.save(path)


def default_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_label(label: str, max_chars: int) -> list[str]:
    parts = label.split()
    lines: list[str] = []
    current = ""
    for part in parts:
        next_value = part if not current else f"{current} {part}"
        if len(next_value) > max_chars and current:
            lines.append(current)
            current = part
        else:
            current = next_value
    if current:
        lines.append(current)
    return lines or [label]


def link_or_copy(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    # COLMAP stores the resolved target path for symlinked images on macOS.
    # The matches importer then cannot find pair-list names from our capture
    # manifest, so research captures must use real files here.
    shutil.copy2(src, dst)


def write_preview(src: Path, dst: Path) -> None:
    with Image.open(src) as image:
        image = image.convert("RGB")
        image.thumbnail((512, 512))
        image.save(dst)


def parse_slot_targets(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


def safe_mean(values: list[Any]) -> float:
    arr = np.asarray([float(value) for value in values if value is not None and math.isfinite(float(value))], dtype=np.float64)
    return float(np.mean(arr)) if arr.size else math.nan


def safe_std(values: list[Any]) -> float:
    arr = np.asarray([float(value) for value in values if value is not None and math.isfinite(float(value))], dtype=np.float64)
    return float(np.std(arr)) if arr.size else math.nan


if __name__ == "__main__":
    raise SystemExit(main())
