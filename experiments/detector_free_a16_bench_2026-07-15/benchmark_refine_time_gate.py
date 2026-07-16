#!/usr/bin/env python3
"""Fair same-process timing gate for coarse versus coarse-to-fine D depth.

Both Dawn pipelines are created by the same shared runtime.  One warm-up of
each variant is discarded, then measured runs use balanced ABBA ordering so
shader compilation, process startup, and order cannot be mistaken for speed.
The phone release gate is intentionally separate: this host run is diagnostic
evidence and never substitutes for the A16 <= 100 ms end-to-end delta gate.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path


EXPERIMENT = Path(__file__).resolve().parent
QUALITY_PATH = EXPERIMENT / "verify_multireference_product_quality.py"


def summarize(samples: list[dict]) -> dict:
    fields = ("wall_ms", "kernel_ms", "session_and_kernel_ms")
    return {
        field: {
            "median": statistics.median(float(sample[field]) for sample in samples),
            "minimum": min(float(sample[field]) for sample in samples),
            "maximum": max(float(sample[field]) for sample in samples),
        }
        for field in fields
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--capture", choices=("cap50", "cap56"), default="cap56")
    parser.add_argument("--reference-index", type=int, default=17)
    parser.add_argument("--blocks", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.blocks < 1:
        parser.error("--blocks must be positive")

    spec = __import__("importlib.util").util.spec_from_file_location(
        "pw_refine_time_gate_quality", QUALITY_PATH
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"cannot load {QUALITY_PATH}")
    quality = __import__("importlib.util").util.module_from_spec(spec)
    __import__("sys").modules[spec.name] = quality
    spec.loader.exec_module(quality)

    depth = quality.load_module(quality.DEPTH_PATH, "pw_refine_time_gate_depth")
    geometry = quality.load_module(
        quality.GEOMETRY_PATH, "pw_refine_time_gate_geometry"
    )
    product = quality.load_module(
        quality.PRODUCT_VERIFY_PATH, "pw_refine_time_gate_cabi"
    )
    library = args.library.resolve()
    api = quality.load_api(product, library)
    frames, sparse_path, planes_path = quality.load_capture(
        depth, geometry, args.capture
    )
    sparse_xyz = depth.read_sparse_xyz(sparse_path)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    def run(variant: str, measured_index: int) -> dict:
        refined = variant == "refined_24x17"
        started = time.perf_counter()
        result = quality.evaluate_reference(
            api,
            product,
            depth,
            frames,
            sparse_xyz,
            planes_path,
            args.capture,
            args.reference_index,
            args.output_dir / variant / f"run_{measured_index:02d}",
            128,
            72,
            24 if refined else 48,
            refined,
            False,
            17,
            1.0,
            False,
            2,
            0.08,
            0.05,
            8.0,
        )
        return {
            "variant": variant,
            "wall_ms": (time.perf_counter() - started) * 1000.0,
            "kernel_ms": sum(result["kernel_ms"]),
            "session_and_kernel_ms": sum(result["session_and_kernel_ms"]),
            "pass": bool(result["pass"]),
            "final_births": int(result["final_births"]),
            "depth_conflict_candidates": int(result["depth_conflict_candidates"]),
            "depth_conflict_candidates_born": int(
                result["depth_conflict_candidates_born"]
            ),
            "final_sparse_error": result["final_sparse_error"],
        }

    warmup = [run("coarse_48", -2), run("refined_24x17", -1)]
    samples: list[dict] = []
    measured_index = 0
    for block in range(args.blocks):
        order = (
            ["coarse_48", "refined_24x17", "refined_24x17", "coarse_48"]
            if block % 2 == 0
            else ["refined_24x17", "coarse_48", "coarse_48", "refined_24x17"]
        )
        for variant in order:
            sample = run(variant, measured_index)
            sample["block"] = block
            sample["order_index"] = measured_index
            samples.append(sample)
            measured_index += 1

    coarse = [sample for sample in samples if sample["variant"] == "coarse_48"]
    refined = [
        sample for sample in samples if sample["variant"] == "refined_24x17"
    ]
    coarse_summary = summarize(coarse)
    refined_summary = summarize(refined)
    deltas = {
        field: refined_summary[field]["median"] - coarse_summary[field]["median"]
        for field in ("wall_ms", "kernel_ms", "session_and_kernel_ms")
    }
    result = {
        "schema": "pocketworld_detector_free_refine_host_time_gate_v1",
        "decision": (
            "PASS_HOST_DIAGNOSTIC_UNDER_100MS"
            if all(sample["pass"] for sample in samples)
            and deltas["session_and_kernel_ms"] <= 100.0
            else "FAIL_HOST_DIAGNOSTIC"
        ),
        "note": "Host diagnostic only; A16 <=100 ms delta is the release gate.",
        "capture": args.capture,
        "reference_index": args.reference_index,
        "library": str(library),
        "library_sha256": quality.sha256(library),
        "blocks": args.blocks,
        "warmup_discarded": warmup,
        "samples": samples,
        "coarse_48": coarse_summary,
        "refined_24x17": refined_summary,
        "refined_minus_coarse_ms": deltas,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["decision"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
