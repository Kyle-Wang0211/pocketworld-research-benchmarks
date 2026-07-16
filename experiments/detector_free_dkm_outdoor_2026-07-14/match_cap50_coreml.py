#!/usr/bin/env python3
"""Run the fixed-shape DKM CoreML matcher over the complete cap50 graph."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import sys
import time
from pathlib import Path

import coremltools as ct
import cv2
import numpy as np
import torch


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(probe_sha256(path)))
    return digest.hexdigest()


def probe_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def connectivity(frame_count: int, rows: list[dict]) -> dict:
    parent = list(range(frame_count))

    def root(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    degree = [0] * frame_count
    reliable = []
    for row in rows:
        if row["magsac_inliers"] < 50 or row["magsac_inlier_ratio"] < 0.8:
            continue
        left, right = row["i"], row["j"]
        first, second = root(left), root(right)
        if first != second:
            parent[second] = first
        degree[left] += 1
        degree[right] += 1
        reliable.append([left, right])
    components: dict[int, list[int]] = {}
    for index in range(frame_count):
        components.setdefault(root(index), []).append(index)
    groups = sorted(components.values(), key=lambda values: (-len(values), values))
    isolated = [index for index, value in enumerate(degree) if value == 0]
    return {
        "gate": "magsac_inliers>=50_and_ratio>=0.8",
        "reliable_edge_count": len(reliable),
        "component_count": len(groups),
        "largest_component_frames": len(groups[0]) if groups else 0,
        "isolated_frames": isolated,
        "minimum_degree": min(degree) if degree else 0,
        "degree": degree,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--neighbors", type=int, default=4)
    parser.add_argument("--min-baseline", type=float, default=0.15)
    parser.add_argument("--max-baseline", type=float, default=1.5)
    parser.add_argument("--max-view-angle", type=float, default=45.0)
    parser.add_argument("--confidence", type=float, default=0.6)
    parser.add_argument("--grid-px", type=int, default=8)
    parser.add_argument("--max-matches", type=int, default=5000)
    parser.add_argument("--sampson-px", type=float, default=3.0)
    parser.add_argument("--memory-guard-gb", type=float, default=3.0)
    parser.add_argument(
        "--pairs",
        nargs="*",
        help="optional explicit frame pairs such as 75:88",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    here = Path(__file__).resolve().parent
    probe = load_module("coreml_cap50_probe", here / "match_cap50.py")
    quality = load_module("coreml_quality_probe", here / "evaluate_coreml_match_quality.py")
    if probe.available_gb() < args.memory_guard_gb:
        raise RuntimeError("memory guard failed before CoreML graph run")
    frames, image_size = probe.load_frames(args.metadata, args.images)
    pairs = probe.select_pairs(
        frames,
        args.min_baseline,
        args.max_baseline,
        args.max_view_angle,
        args.neighbors,
    )
    if args.pairs:
        eligible = {
            (row["i"], row["j"]): row
            for row in probe.select_pairs(
                frames,
                args.min_baseline,
                args.max_baseline,
                args.max_view_angle,
                len(frames),
            )
        }
        requested = []
        for text in args.pairs:
            left, right = sorted(int(value) for value in text.split(":"))
            if (left, right) not in eligible:
                raise ValueError(f"requested pair is outside geometry gate: {text}")
            requested.append(eligible[(left, right)])
        pairs = requested
    args.output_dir.mkdir(parents=True, exist_ok=True)
    load_started = time.perf_counter()
    model = ct.models.MLModel(
        str(args.model), compute_units=ct.ComputeUnit.CPU_AND_GPU
    )
    load_seconds = time.perf_counter() - load_started
    input_shape = tuple(model.get_spec().description.input[0].type.multiArrayType.shape)
    model_height, model_width = input_shape[-2:]
    tensors = {
        frame.index: quality.tensor(frame.path, model_height, model_width)
        for frame in frames
    }
    cv2.setRNGSeed(0)
    rows = []
    arrays = {}
    started = time.perf_counter()
    for pair_index, pair in enumerate(pairs):
        if pair_index % 16 == 0 and probe.available_gb() < args.memory_guard_gb:
            raise RuntimeError(f"memory guard failed at pair {pair_index}")
        left, right = frames[pair["i"]], frames[pair["j"]]
        pair_started = time.perf_counter()
        image0, image1 = tensors[left.index], tensors[right.index]
        raw = model.predict(
            {"image0": image0.numpy(), "image1": image1.numpy()}
        )
        warp, certainty = quality.postprocess(
            {tuple(value.shape): value for value in raw.values()}
        )
        points0, points1, scores, raw_count = probe.deterministic_grid_matches(
            warp,
            certainty,
            image_size,
            args.confidence,
            args.grid_px,
            args.max_matches,
        )
        errors = probe.sampson_error(probe.fundamental(left, right), points0, points1)
        robust_mask = None
        if len(points0) >= 8:
            try:
                _, robust_mask = cv2.findFundamentalMat(
                    points0,
                    points1,
                    cv2.USAC_MAGSAC,
                    args.sampson_px,
                    0.999,
                    10000,
                )
            except cv2.error:
                pass
        robust = (
            robust_mask.reshape(-1).astype(bool)
            if robust_mask is not None
            else np.zeros(len(points0), dtype=bool)
        )
        key = f"{left.index:03d}_{right.index:03d}"
        arrays[f"{key}_p0"] = points0
        arrays[f"{key}_p1"] = points1
        arrays[f"{key}_confidence"] = scores
        arrays[f"{key}_sampson_px"] = errors.astype(np.float32)
        arrays[f"{key}_magsac_inlier"] = robust
        rows.append(
            {
                **pair,
                "raw_above_confidence": raw_count,
                "grid_unique_matches": int(len(points0)),
                "sampson_inliers": int((errors <= args.sampson_px).sum()),
                "sampson_inlier_ratio": float((errors <= args.sampson_px).mean())
                if len(errors)
                else 0.0,
                "magsac_inliers": int(robust.sum()),
                "magsac_inlier_ratio": float(robust.mean()) if len(robust) else 0.0,
                "wall_seconds": time.perf_counter() - pair_started,
            }
        )
        if (pair_index + 1) % 20 == 0 or pair_index + 1 == len(pairs):
            print(
                f"[coreml] {pair_index + 1}/{len(pairs)} "
                f"pair={key} matches={len(points0)}",
                flush=True,
            )
    graph = connectivity(len(frames), rows)
    matches_path = args.output_dir / "matches.npz"
    np.savez_compressed(matches_path, **arrays)
    counts = [row["grid_unique_matches"] for row in rows]
    metadata = {
        "route": "commercial_detector_free_DKMv3_outdoor_CoreML_FP32_fixed_shape",
        "production_ready": False,
        "platform": platform.platform(),
        "coremltools_version": ct.__version__,
        "compute_units": "CPU_AND_GPU",
        "model_tree_sha256": tree_sha256(args.model),
        "model_bytes": sum(path.stat().st_size for path in args.model.rglob("*") if path.is_file()),
        "model_resolution": [model_width, model_height],
        "capture_metadata_sha256": probe_sha256(args.metadata),
        "input_image_count": len(frames),
        "candidate_pair_count": len(pairs),
        "confidence_threshold": args.confidence,
        "grid_px": args.grid_px,
        "sampson_threshold_px": args.sampson_px,
        "model_load_seconds": load_seconds,
        "match_wall_seconds": time.perf_counter() - started,
        "grid_matches_total": int(sum(counts)),
        "grid_matches_median": float(np.median(counts)),
        "zero_match_edges": int(sum(value == 0 for value in counts)),
        "graph": graph,
        "pairs": rows,
        "matches_sha256": probe_sha256(matches_path),
    }
    metrics_path = args.output_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: metadata[key] for key in (
        "candidate_pair_count",
        "grid_matches_total",
        "grid_matches_median",
        "zero_match_edges",
        "match_wall_seconds",
        "graph",
        "matches_sha256",
    )}, indent=2, sort_keys=True))
    print(f"metrics_sha256={probe_sha256(metrics_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
