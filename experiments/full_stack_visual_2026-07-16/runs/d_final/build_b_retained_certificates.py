#!/usr/bin/env python3
"""Bind product B raw PLYs to the actual retained-birth photometric evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np


ASSEMBLER = Path(__file__).resolve().parents[2] / "assemble_full_stack.py"
SPEC = importlib.util.spec_from_file_location("assemble_full_stack", ASSEMBLER)
assert SPEC is not None and SPEC.loader is not None
assembler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = assembler
SPEC.loader.exec_module(assembler)


def sha256(path: Path) -> str:
    return assembler.sha256_file(path)


def file_record(path: Path) -> dict:
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path)}


def load_rows(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"{path}:{line_number}: evidence row is not an object")
        rows.append(row)
    return rows


def load_metric_to_raw(path: Path) -> tuple[float, np.ndarray, np.ndarray, float]:
    document = json.loads(path.read_text(encoding="utf-8"))
    transform = document.get("sim3_metric_to_raw") or document.get("metric_to_raw_sim3")
    if not isinstance(transform, dict):
        raise ValueError("metric-to-raw Sim3 absent")
    scale = float(transform["scale_metric_to_raw"])
    rotation = np.asarray(transform["rotation_metric_to_raw_row_major"], dtype=np.float64).reshape((3, 3))
    translation = np.asarray(transform["translation_metric_to_raw"], dtype=np.float64)
    determinant = float(np.linalg.det(rotation))
    if scale <= 0 or translation.shape != (3,) or not math.isclose(determinant, 1.0, abs_tol=1e-5):
        raise ValueError("metric-to-raw Sim3 malformed")
    tolerance = float(transform.get("float32_derived_tolerance", 1e-4))
    return scale, rotation, translation, tolerance


def planes_by_owner(ownership: dict) -> dict[str, tuple[np.ndarray, float]]:
    result: dict[str, tuple[np.ndarray, float]] = {}
    floor = ownership.get("floor")
    if isinstance(floor, dict):
        result[str(floor["candidate_id"])] = (
            np.asarray(floor["normal"], dtype=np.float64),
            float(floor["plane_value_n_dot_x"]),
        )
    for wall in ownership.get("walls") or []:
        result[str(wall["candidate_id"])] = (
            np.asarray(wall["normal"], dtype=np.float64),
            float(wall["plane_value_n_dot_x"]),
        )
    return result


def transform_plane(
    normal: np.ndarray, plane_value: float, scale: float, rotation: np.ndarray, translation: np.ndarray
) -> tuple[np.ndarray, float]:
    raw_normal = rotation @ normal
    raw_value = scale * plane_value + float(raw_normal @ translation)
    return raw_normal, raw_value


def certify_component(
    *,
    component: str,
    rows: list[dict],
    metric_path: Path,
    raw_path: Path,
    owner_planes: dict[str, tuple[np.ndarray, float]],
    scale: float,
    rotation: np.ndarray,
    translation: np.ndarray,
    transform_tolerance: float,
    source_birth_record: dict,
    output_dir: Path,
) -> tuple[Path, Path]:
    metric = assembler.read_rgb_ply(metric_path)
    raw = assembler.read_rgb_ply(raw_path)
    if len(rows) != len(metric.xyz) or len(rows) != len(raw.xyz) or not rows:
        raise ValueError(f"{component}: row/metric/raw point counts differ")
    row_xyz = np.asarray([row["xyz"] for row in rows], dtype=np.float32).astype(np.float64)
    row_rgb = np.asarray([row["rgb"] for row in rows], dtype=np.uint8)
    if not np.array_equal(row_xyz, metric.xyz) or not np.array_equal(row_rgb, metric.rgb):
        raise ValueError(f"{component}: retained evidence order/payload differs from metric PLY")
    if not np.array_equal(metric.rgb, raw.rgb):
        raise ValueError(f"{component}: raw PLY changed retained RGB/order")
    predicted_raw = scale * (metric.xyz @ rotation.T) + translation
    alignment = np.linalg.norm(predicted_raw - raw.xyz, axis=1)
    if float(np.max(alignment)) > transform_tolerance:
        raise ValueError(f"{component}: raw PLY differs from certified Sim3")

    evidence_rows = []
    xyz_bits = np.ascontiguousarray(raw.xyz.astype("<f4")).view("<u4").reshape((-1, 3))
    for index, (row, xyz) in enumerate(zip(rows, raw.xyz)):
        owner_id = str(row["owner_id"])
        if owner_id not in owner_planes:
            raise ValueError(f"{component}: unknown owner {owner_id}")
        normal, value = owner_planes[owner_id]
        raw_normal, raw_value = transform_plane(normal, value, scale, rotation, translation)
        residual = abs(float(raw_normal @ xyz) - raw_value)
        zncc = float(row["winning_zncc"])
        if not math.isfinite(zncc) or zncc < -1 or zncc > 1:
            raise ValueError(f"{component}: non-physical winning ZNCC")
        evidence_rows.append(
            {
                "output_point_index": index,
                "xyz_f32_bits": [int(value) for value in xyz_bits[index]],
                "source_file_index": 0,
                "source_row_index": int(row["_source_row_index"]),
                "zncc_median": zncc,
                "abs_plane_residual_m": residual,
                "plane_normal_output_gauge": [float(value) for value in raw_normal],
                "plane_value_output_gauge": raw_value,
            }
        )
    zncc_values = np.asarray([row["zncc_median"] for row in evidence_rows], dtype=np.float64)
    residual_values = np.asarray([row["abs_plane_residual_m"] for row in evidence_rows], dtype=np.float64)
    median = float(np.median(zncc_values))
    max_residual = float(np.max(residual_values))
    if median < 0.70 or max_residual > 1e-5:
        raise ValueError(
            f"{component}: retained quality failed (median ZNCC={median}, max residual={max_residual})"
        )

    evidence = {
        "schema": "pw_b_retained_quality_evidence_v1",
        "output_sha256": sha256(raw_path),
        "point_count": len(evidence_rows),
        "source_metric_ply": file_record(metric_path),
        "source_birth_evidence": [source_birth_record],
        "metric_to_raw_alignment": {
            "maximum": float(np.max(alignment)),
            "tolerance": transform_tolerance,
        },
        "rows": evidence_rows,
    }
    evidence_path = output_dir / f"b_{component}_retained_quality_evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    certificate = {
        "schema": "pw_b_dense_planesweep_certificate_v1",
        "status": "PASS",
        "layer": component,
        "config": {"grid_m": 0.01, "ncc_min": 0.70},
        "forbidden_matcher_outputs_consumed": False,
        "gauge": "device_raw",
        "output": file_record(raw_path),
        "totals": {"accepted": len(evidence_rows)},
        "quality": {
            "max_abs_plane_residual_m": max_residual,
            "zncc_median": median,
            "zncc_statistic": "actual_median_of_retained_births",
        },
        "quality_evidence": file_record(evidence_path),
    }
    certificate_path = output_dir / f"b_{component}_provenance.json"
    certificate_path.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return evidence_path, certificate_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-ply", type=Path, required=True)
    parser.add_argument("--raw-floor", type=Path, required=True)
    parser.add_argument("--raw-wall", type=Path, required=True)
    parser.add_argument("--sim3-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    stem = args.export_ply.with_suffix("")
    rows_path = Path(f"{stem}_accepted_evidence.jsonl")
    dense_path = Path(f"{stem}_dense_evidence.json")
    ownership_path = Path(f"{stem}_structural_ownership.json")
    floor_metric = Path(f"{stem}_floor_only.ply")
    wall_metric = Path(f"{stem}_wall_only.ply")
    dense = json.loads(dense_path.read_text(encoding="utf-8"))
    ownership = json.loads(ownership_path.read_text(encoding="utf-8"))
    rows = load_rows(rows_path)
    if dense.get("schema") != "pocketworld_product_b_1cm_dense_evidence_v1" or dense.get("pure_a") is not True:
        raise ValueError("product B dense evidence schema/pure-A flag invalid")
    if dense.get("accepted_evidence_rows") != len(rows):
        raise ValueError("product B dense evidence count mismatch")
    expected_ply = dense.get("ply") or {}
    if expected_ply.get("floor_metric_sha256") != sha256(floor_metric):
        raise ValueError("floor metric PLY hash mismatch")
    if expected_ply.get("wall_metric_sha256") != sha256(wall_metric):
        raise ValueError("wall metric PLY hash mismatch")
    scale, rotation, translation, tolerance = load_metric_to_raw(args.sim3_manifest)
    owner_planes = planes_by_owner(ownership)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    canonical_source_path = args.output_dir / "b_product_birth_evidence_source.jsonl"
    canonical_rows = []
    for source_row_index, row in enumerate(rows):
        row["_source_row_index"] = source_row_index
        canonical_rows.append(
            {
                "component": row["component"],
                "owner_id": row["owner_id"],
                "candidate_index": row["candidate_index"],
                "xyz": row["xyz"],
                "rgb": row["rgb"],
                "zncc_median": row["winning_zncc"],
                "supporting_views": row["supporting_views"],
                "parallax_deg": row["parallax_deg"],
                "depth_margin_m": row["depth_margin_m"],
            }
        )
    canonical_source_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in canonical_rows), encoding="utf-8"
    )
    source_birth_record = file_record(canonical_source_path)
    outputs = []
    for component, metric_path, raw_path in (
        ("floor", floor_metric, args.raw_floor),
        ("wall", wall_metric, args.raw_wall),
    ):
        component_rows = [row for row in rows if row.get("component") == component]
        outputs.extend(
            certify_component(
                component=component,
                rows=component_rows,
                metric_path=metric_path,
                raw_path=raw_path,
                owner_planes=owner_planes,
                scale=scale,
                rotation=rotation,
                translation=translation,
                transform_tolerance=tolerance,
                source_birth_record=source_birth_record,
                output_dir=args.output_dir,
            )
        )
    summary = {str(path): sha256(path) for path in outputs}
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
