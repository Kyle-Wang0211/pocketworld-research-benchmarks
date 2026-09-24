#!/usr/bin/env python3
"""COLMAP-style research executor for DA3 keyframe/window compression.

This is intentionally a research-only evidence generator. COLMAP owns only
feature extraction, pair matching, and geometric verification evidence. Dart
and the PocketWorld pipeline still own production policy.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import sqlite3
import subprocess
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PAIR_ID_BASE = 2147483647


@dataclass(frozen=True)
class FrameInfo:
    frame_id: str
    image_name: str
    image_path: Path
    timestamp: float
    cell_id: str
    quality_score: float
    k_window_weight: float
    azimuth_deg: float
    elevation_deg: float


@dataclass(frozen=True)
class EdgeInfo:
    a: str
    b: str
    raw_matches: int
    inliers: int
    inlier_ratio: float
    config: int
    colmap_score: float
    pose_proxy_score: float
    angular_gap_deg: float
    temporal_gap_s: float

    @property
    def pair_key(self) -> tuple[str, str]:
        return tuple(sorted((self.a, self.b)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--colmap-bin", default="colmap")
    parser.add_argument("--image-subdir", default="photos_depth")
    parser.add_argument("--max-image-size", type=int, default=1000)
    parser.add_argument("--max-num-features", type=int, default=4096)
    parser.add_argument("--view-graph-top-k", type=int, default=12)
    parser.add_argument("--temporal-neighbors", type=int, default=4)
    parser.add_argument("--min-inliers", type=int, default=15)
    parser.add_argument("--bridge-overlap", type=int, default=6)
    parser.add_argument("--slot-targets", default="490,385")
    parser.add_argument("--reuse", action="store_true")
    args = parser.parse_args()

    started = time.time()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / "run_log.jsonl"
    write_jsonl(log_path, {"event": "start", "args": vars_for_json(args)})

    capture_dir = args.capture_dir.resolve()
    bundle = read_json(capture_dir / "photo_bundle.json")
    da3_input = read_json(capture_dir / "da3_input_manifest.json")
    pose_view_graph = read_json(capture_dir / "view_graph.json")
    original_k_windows = read_json(capture_dir / "da3_k_windows.json")
    frames = build_frame_infos(capture_dir, args.image_subdir, bundle, da3_input)
    if len(frames) == 0:
        raise RuntimeError("No frames found for COLMAP executor")

    workspace = args.output_dir / "colmap_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    image_list_path = workspace / "image_list.txt"
    pair_list_path = workspace / "match_pairs.txt"
    db_path = workspace / "database.db"
    write_image_list(image_list_path, frames)
    pairs = build_candidate_pairs(
        frames=frames,
        pose_view_graph=pose_view_graph,
        top_k=args.view_graph_top_k,
        temporal_neighbors=args.temporal_neighbors,
    )
    write_pair_list(pair_list_path, frames, pairs)
    write_jsonl(
        log_path,
        {
            "event": "candidate_pairs",
            "frame_count": len(frames),
            "pair_count": len(pairs),
        },
    )

    if not args.reuse or not db_path.exists():
        if db_path.exists():
            db_path.unlink()
        run_colmap_feature_extractor(args, capture_dir, db_path, image_list_path, log_path)
        run_colmap_matches_importer(args, db_path, pair_list_path, log_path)
    else:
        write_jsonl(log_path, {"event": "reuse_colmap_db", "database": str(db_path)})

    colmap_edges = read_colmap_edges(
        db_path=db_path,
        frame_by_image_name={frame.image_name: frame for frame in frames},
        pose_view_graph=pose_view_graph,
        min_inliers=args.min_inliers,
    )
    frame_scores = score_frames(frames, colmap_edges)
    redundancy = build_redundancy_report(frames, colmap_edges)

    report = build_report(
        args=args,
        frames=frames,
        pairs=pairs,
        colmap_edges=colmap_edges,
        frame_scores=frame_scores,
        redundancy=redundancy,
        elapsed_s=time.time() - started,
    )
    write_json(args.output_dir / "colmap_view_graph_report.json", report)
    write_edges_csv(args.output_dir / "colmap_edges.csv", colmap_edges)
    write_frame_scores_csv(args.output_dir / "frame_scores.csv", frame_scores)

    slot_targets = parse_slot_targets(args.slot_targets)
    plan_summaries: list[dict[str, Any]] = []
    for slot_target in slot_targets:
        plan = build_da3_research_plan(
            original_k_windows=original_k_windows,
            frames=frames,
            frame_scores=frame_scores,
            colmap_edges=colmap_edges,
            slot_target=slot_target,
            bridge_overlap=args.bridge_overlap,
        )
        actual_slots = int(plan["windowCount"]) * int(plan["windowSize"])
        plan_name = f"slots{actual_slots}"
        plan_path = args.output_dir / f"da3_k_windows_colmap_{plan_name}.json"
        overlay_dir = args.output_dir / f"capture_overlay_{plan_name}"
        write_json(plan_path, plan)
        create_capture_overlay(capture_dir, overlay_dir, plan)
        plan_summaries.append(
            {
                "slotTarget": slot_target,
                "actualSlots": actual_slots,
                "overlayDir": str(overlay_dir),
                "planPath": str(plan_path),
                "windowCount": plan["windowCount"],
                "selectedFrameCount": plan["selectedFrameCount"],
                "droppedFrameCount": plan["droppedFrameCount"],
                "bridgeOverlap": args.bridge_overlap,
            }
        )

    write_json(
        args.output_dir / "colmap_candidate_plan_summary.json",
        {
            "schemaVersion": "aether_colmap_candidate_plan_summary_v1",
            "captureDir": str(capture_dir),
            "reportPath": "colmap_view_graph_report.json",
            "planSummaries": plan_summaries,
        },
    )
    write_summary_md(args.output_dir / "summary.md", report, plan_summaries)
    write_jsonl(
        log_path,
        {
            "event": "done",
            "elapsed_s": round(time.time() - started, 3),
            "plans": plan_summaries,
        },
    )
    return 0


def vars_for_json(args: argparse.Namespace) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in vars(args).items():
        out[key] = str(value) if isinstance(value, Path) else value
    return out


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


def build_frame_infos(
    capture_dir: Path,
    image_subdir: str,
    bundle: dict[str, Any],
    da3_input: dict[str, Any],
) -> list[FrameInfo]:
    input_by_id = {str(frame["id"]): frame for frame in da3_input.get("frames", [])}
    frames: list[FrameInfo] = []
    for raw in bundle.get("frames", []):
        frame_id = str(raw.get("id") or "")
        if not frame_id:
            continue
        input_frame = input_by_id.get(frame_id, {})
        image_name = Path(
            str(input_frame.get("depthImageRelativePath") or f"{image_subdir}/{frame_id}.jpg")
        ).name
        image_path = capture_dir / image_subdir / image_name
        if not image_path.exists():
            continue
        quality = raw.get("quality") or {}
        frames.append(
            FrameInfo(
                frame_id=frame_id,
                image_name=image_name,
                image_path=image_path,
                timestamp=float(raw.get("timestamp") or 0.0),
                cell_id=str(raw.get("cellID") or ""),
                quality_score=float(quality.get("score") or 0.0),
                k_window_weight=float(quality.get("kWindowWeight") or quality.get("score") or 0.0),
                azimuth_deg=math.degrees(float(raw.get("azimuth") or 0.0)) % 360.0,
                elevation_deg=math.degrees(float(raw.get("elevation") or 0.0)),
            )
        )
    frames.sort(key=lambda frame: frame.timestamp)
    return frames


def write_image_list(path: Path, frames: list[FrameInfo]) -> None:
    path.write_text("\n".join(frame.image_name for frame in frames) + "\n", encoding="utf-8")


def build_candidate_pairs(
    *,
    frames: list[FrameInfo],
    pose_view_graph: dict[str, Any],
    top_k: int,
    temporal_neighbors: int,
) -> set[tuple[str, str]]:
    valid_ids = {frame.frame_id for frame in frames}
    pairs: set[tuple[str, str]] = set()

    edge_by_node: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for edge in pose_view_graph.get("edges", []):
        a = str(edge.get("sourceID") or "")
        b = str(edge.get("targetID") or "")
        if a not in valid_ids or b not in valid_ids or a == b:
            continue
        score = float(edge.get("score") or 0.0)
        edge_by_node[a].append((b, score))
        edge_by_node[b].append((a, score))
    for a, neighbors in edge_by_node.items():
        neighbors.sort(key=lambda item: item[1], reverse=True)
        for b, _ in neighbors[:top_k]:
            pairs.add(tuple(sorted((a, b))))

    by_time = sorted(frames, key=lambda frame: frame.timestamp)
    for i, frame in enumerate(by_time):
        for j in range(1, temporal_neighbors + 1):
            if i + j >= len(by_time):
                break
            pairs.add(tuple(sorted((frame.frame_id, by_time[i + j].frame_id))))

    return pairs


def write_pair_list(
    path: Path,
    frames: list[FrameInfo],
    pairs: Iterable[tuple[str, str]],
) -> None:
    by_id = {frame.frame_id: frame for frame in frames}
    lines = []
    for a, b in sorted(pairs):
        fa = by_id.get(a)
        fb = by_id.get(b)
        if fa is None or fb is None:
            continue
        lines.append(f"{fa.image_name} {fb.image_name}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_colmap_feature_extractor(
    args: argparse.Namespace,
    capture_dir: Path,
    db_path: Path,
    image_list_path: Path,
    log_path: Path,
) -> None:
    command = [
        args.colmap_bin,
        "feature_extractor",
        "--database_path",
        str(db_path),
        "--image_path",
        str(capture_dir / args.image_subdir),
        "--image_list_path",
        str(image_list_path),
        "--ImageReader.single_camera",
        "1",
        "--ImageReader.camera_model",
        "PINHOLE",
        "--FeatureExtraction.use_gpu",
        "0",
        "--SiftExtraction.max_image_size",
        str(args.max_image_size),
        "--SiftExtraction.max_num_features",
        str(args.max_num_features),
    ]
    run_command(command, log_path, "colmap_feature_extractor")


def run_colmap_matches_importer(
    args: argparse.Namespace,
    db_path: Path,
    pair_list_path: Path,
    log_path: Path,
) -> None:
    command = [
        args.colmap_bin,
        "matches_importer",
        "--database_path",
        str(db_path),
        "--match_list_path",
        str(pair_list_path),
        "--match_type",
        "pairs",
        "--FeatureMatching.use_gpu",
        "0",
        "--TwoViewGeometry.min_num_inliers",
        str(args.min_inliers),
        "--TwoViewGeometry.compute_relative_pose",
        "1",
    ]
    run_command(command, log_path, "colmap_matches_importer")


def run_command(command: list[str], log_path: Path, event: str) -> None:
    started = time.time()
    write_jsonl(log_path, {"event": f"{event}_start", "command": command})
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    write_jsonl(
        log_path,
        {
            "event": f"{event}_done",
            "returncode": proc.returncode,
            "elapsed_s": round(time.time() - started, 3),
            "tail": proc.stdout[-6000:],
        },
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{event} failed with exit code {proc.returncode}\n{proc.stdout[-4000:]}")


def read_colmap_edges(
    *,
    db_path: Path,
    frame_by_image_name: dict[str, FrameInfo],
    pose_view_graph: dict[str, Any],
    min_inliers: int,
) -> list[EdgeInfo]:
    pose_score_by_pair: dict[tuple[str, str], tuple[float, float, float]] = {}
    for edge in pose_view_graph.get("edges", []):
        a = str(edge.get("sourceID") or "")
        b = str(edge.get("targetID") or "")
        if not a or not b:
            continue
        key = tuple(sorted((a, b)))
        pose_score_by_pair[key] = (
            float(edge.get("score") or 0.0),
            float(edge.get("angularGapDeg") or 0.0),
            float(edge.get("temporalGapSec") or 0.0),
        )

    conn = sqlite3.connect(str(db_path))
    try:
        image_name_by_id = {
            int(row[0]): str(row[1]) for row in conn.execute("select image_id, name from images")
        }
        frame_id_by_image_id = {
            image_id: frame_by_image_name[name].frame_id
            for image_id, name in image_name_by_id.items()
            if name in frame_by_image_name
        }

        raw_matches_by_pair: dict[int, int] = {}
        if table_exists(conn, "matches"):
            for pair_id, rows in conn.execute("select pair_id, rows from matches"):
                raw_matches_by_pair[int(pair_id)] = int(rows or 0)

        edges: list[EdgeInfo] = []
        for row in conn.execute("select pair_id, rows, config from two_view_geometries"):
            pair_id = int(row[0])
            inliers = int(row[1] or 0)
            config = int(row[2] or 0)
            image_id1, image_id2 = pair_id_to_image_ids(pair_id)
            a = frame_id_by_image_id.get(image_id1)
            b = frame_id_by_image_id.get(image_id2)
            if not a or not b or a == b:
                continue
            raw = raw_matches_by_pair.get(pair_id, 0)
            ratio = float(inliers) / raw if raw > 0 else 0.0
            pose_score, angular_gap, temporal_gap = pose_score_by_pair.get(
                tuple(sorted((a, b))),
                (0.0, 0.0, 0.0),
            )
            score = 0.0
            if inliers >= min_inliers and config != 0:
                score = math.log1p(inliers) * 0.68 + min(1.0, ratio) * 2.0 + pose_score * 0.35
            edges.append(
                EdgeInfo(
                    a=a,
                    b=b,
                    raw_matches=raw,
                    inliers=inliers,
                    inlier_ratio=ratio,
                    config=config,
                    colmap_score=score,
                    pose_proxy_score=pose_score,
                    angular_gap_deg=angular_gap,
                    temporal_gap_s=temporal_gap,
                )
            )
        edges.sort(key=lambda edge: edge.colmap_score, reverse=True)
        return edges
    finally:
        conn.close()


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "select name from sqlite_master where type='table' and name=?", (table,)
    ).fetchone()
    return row is not None


def pair_id_to_image_ids(pair_id: int) -> tuple[int, int]:
    image_id2 = pair_id % PAIR_ID_BASE
    image_id1 = (pair_id - image_id2) // PAIR_ID_BASE
    return image_id1, image_id2


def score_frames(frames: list[FrameInfo], edges: list[EdgeInfo]) -> list[dict[str, Any]]:
    by_id = {frame.frame_id: frame for frame in frames}
    stats: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for edge in edges:
        if edge.inliers <= 0:
            continue
        verified = 1.0 if edge.colmap_score > 0.0 else 0.0
        for frame_id in (edge.a, edge.b):
            stats[frame_id]["raw_match_sum"] += edge.raw_matches
            stats[frame_id]["inlier_sum"] += edge.inliers
            stats[frame_id]["verified_degree"] += verified
            stats[frame_id]["candidate_degree"] += 1.0
            stats[frame_id]["max_inliers"] = max(stats[frame_id]["max_inliers"], edge.inliers)

    max_log_inliers = max([math.log1p(v["inlier_sum"]) for v in stats.values()] + [1.0])
    max_degree = max([v["verified_degree"] for v in stats.values()] + [1.0])
    rows: list[dict[str, Any]] = []
    for frame in frames:
        stat = stats[frame.frame_id]
        colmap_strength = math.log1p(stat["inlier_sum"]) / max_log_inliers
        degree_strength = stat["verified_degree"] / max_degree
        quality = frame.k_window_weight or frame.quality_score
        score = 0.48 * colmap_strength + 0.24 * degree_strength + 0.22 * quality
        score += 0.06 * min(1.0, stat["max_inliers"] / 500.0)
        rows.append(
            {
                "frameID": frame.frame_id,
                "imageName": frame.image_name,
                "cellID": frame.cell_id,
                "timestamp": frame.timestamp,
                "qualityScore": frame.quality_score,
                "kWindowWeight": frame.k_window_weight,
                "verifiedDegree": int(stat["verified_degree"]),
                "candidateDegree": int(stat["candidate_degree"]),
                "inlierSum": int(stat["inlier_sum"]),
                "rawMatchSum": int(stat["raw_match_sum"]),
                "maxInliers": int(stat["max_inliers"]),
                "colmapStrength": colmap_strength,
                "degreeStrength": degree_strength,
                "keyframeScore": score,
                "azimuthDeg": frame.azimuth_deg,
                "elevationDeg": frame.elevation_deg,
            }
        )
    rows.sort(key=lambda row: float(row["keyframeScore"]), reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows


def build_redundancy_report(frames: list[FrameInfo], edges: list[EdgeInfo]) -> dict[str, Any]:
    frame_by_id = {frame.frame_id: frame for frame in frames}
    strong_edges = [
        edge
        for edge in edges
        if edge.inliers >= 180 and edge.inlier_ratio >= 0.35 and edge.angular_gap_deg <= 8.0
    ]
    parent = {frame.frame_id: frame.frame_id for frame in frames}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    for edge in strong_edges:
        if edge.a in parent and edge.b in parent:
            union(edge.a, edge.b)

    groups: dict[str, list[str]] = defaultdict(list)
    for frame in frames:
        groups[find(frame.frame_id)].append(frame.frame_id)
    redundant_groups = []
    for members in groups.values():
        if len(members) < 3:
            continue
        redundant_groups.append(
            {
                "frameIDs": sorted(members),
                "frameCount": len(members),
                "cellIDs": sorted({frame_by_id[m].cell_id for m in members if m in frame_by_id}),
            }
        )
    redundant_groups.sort(key=lambda item: item["frameCount"], reverse=True)
    return {
        "strongNearDuplicateEdgeCount": len(strong_edges),
        "redundantGroupCount": len(redundant_groups),
        "largestGroups": redundant_groups[:20],
        "rule": "research proxy: high COLMAP inliers + high inlier ratio + small AR angular gap",
    }


def build_report(
    *,
    args: argparse.Namespace,
    frames: list[FrameInfo],
    pairs: set[tuple[str, str]],
    colmap_edges: list[EdgeInfo],
    frame_scores: list[dict[str, Any]],
    redundancy: dict[str, Any],
    elapsed_s: float,
) -> dict[str, Any]:
    verified = [edge for edge in colmap_edges if edge.colmap_score > 0]
    frame_with_verified = {
        frame_id
        for edge in verified
        for frame_id in (edge.a, edge.b)
    }
    return {
        "schemaVersion": "aether_colmap_view_graph_research_report_v1",
        "status": "completed",
        "captureDir": str(args.capture_dir),
        "imageSubdir": args.image_subdir,
        "executorBoundary": {
            "role": "research_evidence_only",
            "colmapOwns": [
                "SIFT feature extraction",
                "candidate pair matching",
                "two-view geometric verification",
            ],
            "dartStillOwns": [
                "production frame acceptance",
                "DA3 K-window policy",
                "quality gates",
                "downstream consumption rules",
            ],
        },
        "licenseAudit": {
            "colmap": "COLMAP binary, New BSD core; production bundling must audit dependencies separately",
            "thisExecutor": "research wrapper only; not shipped in mobile app",
        },
        "settings": {
            "viewGraphTopK": args.view_graph_top_k,
            "temporalNeighbors": args.temporal_neighbors,
            "minInliers": args.min_inliers,
            "bridgeOverlap": args.bridge_overlap,
            "maxImageSize": args.max_image_size,
            "maxNumFeatures": args.max_num_features,
        },
        "counts": {
            "frameCount": len(frames),
            "candidatePairCount": len(pairs),
            "matchedPairCount": len(colmap_edges),
            "verifiedPairCount": len(verified),
            "framesWithVerifiedEdges": len(frame_with_verified),
        },
        "topFrames": frame_scores[:40],
        "topEdges": [edge_to_json(edge) for edge in verified[:80]],
        "redundancy": redundancy,
        "elapsedS": round(elapsed_s, 3),
    }


def build_da3_research_plan(
    *,
    original_k_windows: dict[str, Any],
    frames: list[FrameInfo],
    frame_scores: list[dict[str, Any]],
    colmap_edges: list[EdgeInfo],
    slot_target: int,
    bridge_overlap: int,
) -> dict[str, Any]:
    window_size = int(original_k_windows.get("windowSize") or 35)
    window_count = max(1, slot_target // window_size)
    actual_slots = window_count * window_size
    bridge_overlap = min(max(0, bridge_overlap), window_size - 1)
    unique_capacity = window_size + max(0, window_count - 1) * (window_size - bridge_overlap)
    selected_scores = frame_scores[: min(len(frame_scores), unique_capacity)]
    candidate_ids = [str(row["frameID"]) for row in selected_scores]
    score_by_id = {str(row["frameID"]): float(row["keyframeScore"]) for row in frame_scores}
    frame_by_id = {frame.frame_id: frame for frame in frames}
    adjacency = build_adjacency(colmap_edges)

    windows: list[dict[str, Any]] = []
    bridge_graph: list[dict[str, Any]] = []
    covered: set[str] = set()
    candidate_set = set(candidate_ids)

    for window_index in range(window_count):
        parent = None
        bridge: list[str] = []
        if window_index == 0:
            seed = next((fid for fid in candidate_ids if fid not in covered), candidate_ids[0])
        else:
            seed = choose_connected_seed(candidate_ids, covered, windows, adjacency, score_by_id)
            parent = choose_parent_window(seed, windows, adjacency)
            if parent is not None:
                bridge = select_bridge(parent, seed, adjacency, score_by_id, bridge_overlap)

        core_count = window_size - len(bridge)
        core = expand_patch(
            seed=seed,
            target_count=core_count,
            candidates=candidate_ids,
            candidate_set=candidate_set,
            covered=covered,
            excluded=set(bridge),
            adjacency=adjacency,
            score_by_id=score_by_id,
        )
        frame_ids = list(bridge)
        for fid in core:
            if fid not in frame_ids:
                frame_ids.append(fid)
        if not frame_ids:
            break
        pad_index = 0
        while len(frame_ids) < window_size:
            frame_ids.append(frame_ids[pad_index % len(frame_ids)])
            pad_index += 1
        unique_ids = list(dict.fromkeys(frame_ids))
        covered.update(unique_ids)
        window_id = f"window_{window_index:03d}"
        parent_id = str(parent.get("id")) if parent else ""
        window = {
            "id": window_id,
            "modelTag": original_k_windows.get("model", {}).get("mobileTag"),
            "modelResourceName": original_k_windows.get("model", {}).get("resourceName"),
            "selectionMode": "colmap_verified_view_graph_keyframe_research_v1",
            "frameIDs": frame_ids,
            "uniqueFrameIDs": unique_ids,
            "coreFrameIDs": core,
            "bridgeFrameIDs": bridge,
            "seedFrameID": seed,
            "frameCount": len(frame_ids),
            "uniqueFrameCount": len(unique_ids),
            "coreFrameCount": len(core),
            "bridgeFrameCount": len(bridge),
            "bridgeTargetFrameCount": bridge_overlap,
            "bridgeRule": "root_window_no_parent" if parent is None else "colmap_verified_bridge_from_parent_window",
            "bridgeValidation": {
                "status": "root" if parent is None else "candidate_requires_downstream_dense_sim3",
                "evidence": "COLMAP two-view verified inlier graph",
            },
            "paddedToWindowSize": len(frame_ids) > len(unique_ids),
            "inputHeight": original_k_windows.get("inputHeight"),
            "inputWidth": original_k_windows.get("inputWidth"),
        }
        if parent_id:
            window["parentWindowID"] = parent_id
            bridge_graph.append(
                {
                    "sourceWindowID": parent_id,
                    "targetWindowID": window_id,
                    "kind": "tree_bridge",
                    "bridgeFrameIDs": bridge,
                    "bridgeFrameCount": len(bridge),
                    "status": "pending_dense_sim3_verification",
                    "alignMethod": "dense_sim3",
                    "evidence": "colmap_verified_view_graph",
                }
            )
        windows.append(window)

    selected_frame_ids = sorted({fid for window in windows for fid in window["uniqueFrameIDs"]})
    all_frame_ids = {frame.frame_id for frame in frames}
    dropped_frame_ids = sorted(all_frame_ids - set(selected_frame_ids))
    loop_candidates = build_loop_candidates(windows, adjacency, bridge_graph)
    return {
        "schemaVersion": "aether_da3_k_windows_v1",
        "sourceManifest": "photo_bundle.json",
        "sourceViewGraph": "colmap_view_graph_report.json",
        "model": original_k_windows.get("model", {}),
        "windowSize": window_size,
        "windowingPolicy": {
            "kind": "colmap_verified_view_graph_keyframe_research_v1",
            "productionAllowed": False,
            "temporalOrderRole": "tie_breaker_only_not_topology",
            "slotTarget": slot_target,
            "actualSlots": actual_slots,
            "targetBridgeOverlap": bridge_overlap,
            "stepEquivalent": window_size - bridge_overlap,
            "keyframeSource": "COLMAP SIFT matches_importer two-view geometric verification",
            "coverageRule": "research keyframe subset; dropped frames are intentional for compression test",
            "selectionBoundary": "external executor returns raw evidence; Dart/product policy not changed",
        },
        "loopClosurePolicy": original_k_windows.get("loopClosurePolicy", {}),
        "inputSizeLocked": original_k_windows.get("inputSizeLocked", True),
        "inputHeight": original_k_windows.get("inputHeight"),
        "inputWidth": original_k_windows.get("inputWidth"),
        "bridgeGraph": bridge_graph,
        "loopCandidates": loop_candidates,
        "uncoveredFrameIDs": dropped_frame_ids,
        "uncoveredFrameCount": len(dropped_frame_ids),
        "selectedFrameIDs": selected_frame_ids,
        "selectedFrameCount": len(selected_frame_ids),
        "droppedFrameIDs": dropped_frame_ids,
        "droppedFrameCount": len(dropped_frame_ids),
        "windowCount": len(windows),
        "windows": windows,
        "diagnostics": {
            "candidateCapacity": unique_capacity,
            "requestedWindowCount": window_count,
            "actualSlots": actual_slots,
            "meanKeyframeScoreSelected": mean([score_by_id.get(fid, 0.0) for fid in selected_frame_ids]),
            "meanKeyframeScoreDropped": mean([score_by_id.get(fid, 0.0) for fid in dropped_frame_ids]),
        },
    }


def build_adjacency(edges: list[EdgeInfo]) -> dict[str, list[tuple[str, float, int]]]:
    adjacency: dict[str, list[tuple[str, float, int]]] = defaultdict(list)
    for edge in edges:
        score = edge.colmap_score
        if score <= 0.0:
            continue
        adjacency[edge.a].append((edge.b, score, edge.inliers))
        adjacency[edge.b].append((edge.a, score, edge.inliers))
    for neighbors in adjacency.values():
        neighbors.sort(key=lambda item: item[1], reverse=True)
    return adjacency


def choose_connected_seed(
    candidate_ids: list[str],
    covered: set[str],
    windows: list[dict[str, Any]],
    adjacency: dict[str, list[tuple[str, float, int]]],
    score_by_id: dict[str, float],
) -> str:
    existing = {fid for window in windows for fid in window.get("uniqueFrameIDs", [])}
    best_id = ""
    best_score = -1.0
    for fid in candidate_ids:
        if fid in covered:
            continue
        connection = sum(score for other, score, _ in adjacency.get(fid, []) if other in existing)
        score = score_by_id.get(fid, 0.0) + connection * 0.12
        if score > best_score:
            best_id = fid
            best_score = score
    if best_id:
        return best_id
    return next((fid for fid in candidate_ids if fid not in covered), candidate_ids[0])


def choose_parent_window(
    seed: str,
    windows: list[dict[str, Any]],
    adjacency: dict[str, list[tuple[str, float, int]]],
) -> dict[str, Any] | None:
    neighbor_score = {other: score for other, score, _ in adjacency.get(seed, [])}
    best: dict[str, Any] | None = None
    best_score = -1.0
    for window in windows:
        score = sum(neighbor_score.get(fid, 0.0) for fid in window.get("uniqueFrameIDs", []))
        if score > best_score:
            best = window
            best_score = score
    return best


def select_bridge(
    parent: dict[str, Any],
    seed: str,
    adjacency: dict[str, list[tuple[str, float, int]]],
    score_by_id: dict[str, float],
    target_count: int,
) -> list[str]:
    if target_count <= 0:
        return []
    neighbor_score = {other: score for other, score, _ in adjacency.get(seed, [])}
    ranked = list(parent.get("uniqueFrameIDs", []))
    ranked.sort(key=lambda fid: (neighbor_score.get(fid, 0.0), score_by_id.get(fid, 0.0)), reverse=True)
    return ranked[:target_count]


def expand_patch(
    *,
    seed: str,
    target_count: int,
    candidates: list[str],
    candidate_set: set[str],
    covered: set[str],
    excluded: set[str],
    adjacency: dict[str, list[tuple[str, float, int]]],
    score_by_id: dict[str, float],
) -> list[str]:
    selected: list[str] = []
    used = set(excluded)
    for prefer_uncovered in (True, False):
        queue = deque([seed])
        seen_in_pass: set[str] = set()
        while queue and len(selected) < target_count:
            fid = queue.popleft()
            if fid in seen_in_pass:
                continue
            seen_in_pass.add(fid)
            if fid in used or fid not in candidate_set:
                continue
            if prefer_uncovered and fid in covered and fid != seed:
                continue
            selected.append(fid)
            used.add(fid)
            neighbors = adjacency.get(fid, [])[:32]
            ranked = sorted(
                neighbors,
                key=lambda item: (
                    0 if item[0] in covered else 1,
                    item[1],
                    score_by_id.get(item[0], 0.0),
                ),
                reverse=True,
            )
            for other, _, _ in ranked:
                if other not in used and other in candidate_set:
                    queue.append(other)
        if len(selected) >= target_count:
            break

    if len(selected) < target_count:
        fallback = [fid for fid in candidates if fid not in used]
        fallback.sort(
            key=lambda fid: (
                0 if fid in covered else 1,
                score_by_id.get(fid, 0.0),
            ),
            reverse=True,
        )
        for fid in fallback:
            if len(selected) >= target_count:
                break
            selected.append(fid)
            used.add(fid)
    return selected[:target_count]


def build_loop_candidates(
    windows: list[dict[str, Any]],
    adjacency: dict[str, list[tuple[str, float, int]]],
    bridge_graph: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tree_pairs = {
        tuple(sorted((str(edge["sourceWindowID"]), str(edge["targetWindowID"]))))
        for edge in bridge_graph
    }
    edge_score: dict[tuple[str, str], float] = {}
    for a, neighbors in adjacency.items():
        for b, score, _ in neighbors:
            edge_score[tuple(sorted((a, b)))] = max(
                edge_score.get(tuple(sorted((a, b))), 0.0),
                score,
            )
    candidates = []
    for i, wa in enumerate(windows):
        for wb in windows[i + 1 :]:
            pair = tuple(sorted((str(wa["id"]), str(wb["id"]))))
            if pair in tree_pairs:
                continue
            a_frames = list(wa.get("uniqueFrameIDs", []))
            b_frames = list(wb.get("uniqueFrameIDs", []))
            shared = sorted(set(a_frames).intersection(b_frames))
            cross = 0.0
            for a in a_frames:
                for b in b_frames:
                    cross = max(cross, edge_score.get(tuple(sorted((a, b))), 0.0))
            if len(shared) >= 3 or cross > 3.7:
                candidates.append(
                    {
                        "sourceWindowID": wa["id"],
                        "targetWindowID": wb["id"],
                        "sharedFrameIDs": shared,
                        "sharedFrameCount": len(shared),
                        "colmapCrossScore": cross,
                        "status": "pending_dense_sim3",
                        "geometryVerification": {
                            "required": True,
                            "method": "dense_sim3_alignment",
                        },
                    }
                )
    candidates.sort(key=lambda item: (item["sharedFrameCount"], item["colmapCrossScore"]), reverse=True)
    return candidates[:64]


def create_capture_overlay(capture_dir: Path, overlay_dir: Path, plan: dict[str, Any]) -> None:
    overlay_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "photo_bundle.json",
        "da3_input_manifest.json",
        "model_policy.json",
        "view_graph.json",
        "bundle_validation.json",
    ]:
        src = capture_dir / name
        dst = overlay_dir / name
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        if src.exists():
            os.symlink(src, dst)
    for name in ["photos_depth", "photos_highres", "previews", "colmap"]:
        src = capture_dir / name
        dst = overlay_dir / name
        if dst.exists() or dst.is_symlink():
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        if src.exists():
            os.symlink(src, dst)
    write_json(overlay_dir / "da3_k_windows.json", plan)


def parse_slot_targets(raw: str) -> list[int]:
    values = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        values.append(int(part))
    return values or [490, 385]


def edge_to_json(edge: EdgeInfo) -> dict[str, Any]:
    return {
        "sourceID": edge.a,
        "targetID": edge.b,
        "rawMatches": edge.raw_matches,
        "inliers": edge.inliers,
        "inlierRatio": edge.inlier_ratio,
        "config": edge.config,
        "colmapScore": edge.colmap_score,
        "poseProxyScore": edge.pose_proxy_score,
        "angularGapDeg": edge.angular_gap_deg,
        "temporalGapS": edge.temporal_gap_s,
    }


def write_edges_csv(path: Path, edges: list[EdgeInfo]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "sourceID",
                "targetID",
                "rawMatches",
                "inliers",
                "inlierRatio",
                "config",
                "colmapScore",
                "poseProxyScore",
                "angularGapDeg",
                "temporalGapS",
            ],
        )
        writer.writeheader()
        for edge in edges:
            writer.writerow(edge_to_json(edge))


def write_frame_scores_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_summary_md(
    path: Path,
    report: dict[str, Any],
    plan_summaries: list[dict[str, Any]],
) -> None:
    counts = report["counts"]
    lines = [
        "# COLMAP-Style View Graph Research Executor",
        "",
        "This report is research-only. COLMAP generates visual/geometric evidence; it does not own production capture or DA3 policy.",
        "",
        "## Evidence Counts",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| frames | {counts['frameCount']} |",
        f"| candidate pairs | {counts['candidatePairCount']} |",
        f"| matched pairs | {counts['matchedPairCount']} |",
        f"| verified pairs | {counts['verifiedPairCount']} |",
        f"| frames with verified edges | {counts['framesWithVerifiedEdges']} |",
        "",
        "## Candidate DA3 Plans",
        "",
        "| plan | windows | slots | selected frames | dropped frames | overlay |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for plan in plan_summaries:
        lines.append(
            f"| target {plan['slotTarget']} | {plan['windowCount']} | {plan['actualSlots']} | "
            f"{plan['selectedFrameCount']} | {plan['droppedFrameCount']} | `{plan['overlayDir']}` |"
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


if __name__ == "__main__":
    raise SystemExit(main())
