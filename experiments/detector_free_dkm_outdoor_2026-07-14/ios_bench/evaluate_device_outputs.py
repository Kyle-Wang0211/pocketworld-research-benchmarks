#!/usr/bin/env python3
"""Compare fixed-shape iOS DKM outputs with the locked host reference."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def raw_metrics(device: np.ndarray, reference: np.ndarray) -> dict:
    if device.shape != reference.shape:
        raise ValueError(f"output shape mismatch: {device.shape} != {reference.shape}")
    delta = np.abs(device - reference)
    return {
        "count": int(device.size),
        "all_finite": bool(np.isfinite(device).all()),
        "max_abs": float(delta.max()),
        "mean_abs": float(delta.mean()),
        "p95_abs": float(np.quantile(delta, 0.95)),
        "p99_abs": float(np.quantile(delta, 0.99)),
    }


def serializable_variant(values: dict) -> dict:
    return {
        key: value
        for key, value in values.items()
        if key not in {"points0", "points1"}
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--pair", default="0:1")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=288)
    parser.add_argument("--confidence", type=float, default=0.6)
    parser.add_argument("--grid-px", type=int, default=8)
    parser.add_argument("--sampson-px", type=float, default=3.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    experiment = Path(__file__).resolve().parent.parent
    probe = load_module("ios_dkm_probe", experiment / "match_cap50.py")
    quality = load_module(
        "ios_dkm_quality", experiment / "evaluate_coreml_match_quality.py"
    )
    left_index, right_index = (int(value) for value in args.pair.split(":"))
    frames, image_size = probe.load_frames(args.metadata, args.images)
    shapes = {
        "flow": (2, 2, args.height, args.width),
        "certainty": (2, 1, args.height, args.width),
        "low_certainty": (2, 1, args.height // 16, args.width // 16),
    }
    reference_names = {
        "flow": "reference_flow.f32",
        "certainty": "reference_certainty.f32",
        "low_certainty": "reference_low_certainty.f32",
    }
    raw: dict[str, dict[tuple[int, ...], np.ndarray]] = {
        "a16": {},
        "m3": {},
    }
    raw_report = {}
    file_hashes = {}
    for name, shape in shapes.items():
        device_path = args.device_dir / f"cold_{name}.f32"
        reference_path = args.reference_dir / reference_names[name]
        device = np.fromfile(device_path, dtype=np.float32).reshape(shape)
        reference = np.fromfile(reference_path, dtype=np.float32).reshape(shape)
        raw["a16"][shape] = device
        raw["m3"][shape] = reference
        raw_report[name] = raw_metrics(device, reference)
        file_hashes[name] = {
            "a16_sha256": sha256(device_path),
            "m3_sha256": sha256(reference_path),
        }

    variants = {}
    cv2.setRNGSeed(0)
    for platform, values in raw.items():
        warp, certainty = quality.postprocess(values)
        points0, points1, _scores, raw_count = probe.deterministic_grid_matches(
            warp,
            certainty,
            image_size,
            args.confidence,
            args.grid_px,
            5000,
        )
        errors = probe.sampson_error(
            probe.fundamental(frames[left_index], frames[right_index]),
            points0,
            points1,
        )
        variants[platform] = {
            "points0": points0,
            "points1": points1,
            "raw_above_confidence": raw_count,
            "selected_matches": len(points0),
            "arkit_inliers": int((errors <= args.sampson_px).sum()),
            "arkit_inlier_ratio": float((errors <= args.sampson_px).mean())
            if len(errors)
            else 0.0,
            **quality.robust_metrics(points0, points1, args.sampson_px),
        }

    a16_cells = quality.selected_cells(
        variants["a16"]["points0"], variants["a16"]["points1"], args.grid_px
    )
    m3_cells = quality.selected_cells(
        variants["m3"]["points0"], variants["m3"]["points1"], args.grid_px
    )
    common = sorted(a16_cells.keys() & m3_cells.keys())
    union = a16_cells.keys() | m3_cells.keys()
    endpoint = np.asarray(
        [np.linalg.norm(a16_cells[cell] - m3_cells[cell]) for cell in common]
    )
    raw_thresholds = {
        "flow_max_abs": 5e-5,
        "certainty_max_abs": 1e-3,
        "low_certainty_max_abs": 2e-5,
    }
    raw_strict_pass = (
        raw_report["flow"]["max_abs"] <= raw_thresholds["flow_max_abs"]
        and raw_report["certainty"]["max_abs"]
        <= raw_thresholds["certainty_max_abs"]
        and raw_report["low_certainty"]["max_abs"]
        <= raw_thresholds["low_certainty_max_abs"]
    )
    filtered_match_pass = (
        len(common) == len(union)
        and variants["a16"]["selected_matches"]
        == variants["m3"]["selected_matches"]
        and variants["a16"]["arkit_inliers"] == variants["m3"]["arkit_inliers"]
        and variants["a16"]["magsac_inliers"]
        == variants["m3"]["magsac_inliers"]
    )
    if filtered_match_pass and raw_strict_pass:
        decision = "PASS_RAW_AND_FILTERED_MATCH_PARITY"
    elif filtered_match_pass:
        decision = "PASS_FILTERED_MATCH_PARITY_RAW_STRICT_GATE_MISS"
    else:
        decision = "FAIL_FILTERED_MATCH_PARITY"
    report = {
        "decision": decision,
        "pair": [left_index, right_index],
        "input_resolution": [args.width, args.height],
        "confidence": args.confidence,
        "grid_px": args.grid_px,
        "sampson_px": args.sampson_px,
        "raw_thresholds": raw_thresholds,
        "raw_strict_pass": raw_strict_pass,
        "raw": raw_report,
        "file_hashes": file_hashes,
        "filtered_match_pass": filtered_match_pass,
        "variants": {
            name: serializable_variant(values) for name, values in variants.items()
        },
        "selected_cell_intersection": len(common),
        "selected_cell_union": len(union),
        "selected_cell_jaccard": len(common) / len(union) if union else 1.0,
        "endpoint_delta_px_original": {
            "median": float(np.median(endpoint)) if len(endpoint) else None,
            "p90": float(np.quantile(endpoint, 0.9)) if len(endpoint) else None,
            "p99": float(np.quantile(endpoint, 0.99)) if len(endpoint) else None,
            "max": float(endpoint.max()) if len(endpoint) else None,
            "over_0_1px": int((endpoint > 0.1).sum()),
            "over_1px": int((endpoint > 1.0).sum()),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if filtered_match_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
