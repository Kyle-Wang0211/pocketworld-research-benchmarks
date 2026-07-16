#!/usr/bin/env python3
"""Fail-closed normalization for final-stack D execution certificates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


COMMERCIAL_CLEAN = {
    "forbidden_matcher_outputs_consumed": False,
    "jpeg_backend": "libjpeg_turbo_product",
    "loftr_consumed": False,
    "method": (
        "self-developed multiview photometric depth sweep + reciprocal "
        "consistency + reference-certified local-manifold birth gate"
    ),
    "model_weights_consumed": False,
    "scannet_consumed": False,
}

ALLOWED_SOURCE_STATUSES = {
    "PASS_EXACT_D_NEW_FINAL_INPUT",
    "PASS_INPUT_EXACT_COMMERCIAL_CLEAN_PARTIAL_ASSETS",
}

FORBIDDEN_IMPLEMENTATION_TOKENS = re.compile(
    r"(?i)\b(?:loftr|scannet|onnx|coreml|pytorch|torchscript)\b"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record(path: Path, *, point_count: int | None = None) -> dict:
    result = {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }
    if point_count is not None:
        result["point_count"] = point_count
    return result


def ply_point_count(path: Path) -> int:
    with path.open("rb") as handle:
        for raw in handle:
            line = raw.decode("ascii").strip()
            if line.startswith("element vertex "):
                return int(line.rsplit(" ", 1)[1])
            if line == "end_header":
                break
    raise ValueError(f"{path}: PLY vertex count absent")


def validate_record(bound: dict, path: Path) -> None:
    if bound.get("sha256") != sha256(path) or bound.get("bytes") != path.stat().st_size:
        raise ValueError(f"{path}: bound hash/size mismatch")


def validate_source_status(source: dict) -> None:
    if source.get("status") not in ALLOWED_SOURCE_STATUSES:
        raise ValueError("source exact-D status is not an allowed PASS")


def validate_output_counts(execution: dict, replay_count: int, metric_count: int) -> None:
    if replay_count != metric_count or replay_count != execution.get("final_births"):
        raise ValueError("D output count differs from certified final births")


def validate_commercial_clean_source(source: dict, execution_document: dict, audited_paths: list[Path]) -> dict:
    declared = source.get("commercial_clean")
    if isinstance(declared, dict):
        for key in (
            "forbidden_matcher_outputs_consumed",
            "loftr_consumed",
            "model_weights_consumed",
            "scannet_consumed",
        ):
            if declared.get(key) is not False:
                raise ValueError(f"source commercial-clean flag conflicts: {key}")
        if declared.get("jpeg_backend") != "libjpeg_turbo_product":
            raise ValueError("source commercial-clean JPEG backend conflicts")
    elif declared is not True:
        raise ValueError("source certificate does not declare commercial-clean execution")

    immutable = execution_document.get("immutable_inputs")
    if not isinstance(immutable, dict) or immutable.get("jpeg_backend_label") != "libjpeg_turbo_product":
        raise ValueError("execution did not use the certified libjpeg product backend")
    scans = []
    for path in audited_paths:
        text = path.read_text(encoding="utf-8")
        matches = sorted(set(match.group(0).lower() for match in FORBIDDEN_IMPLEMENTATION_TOKENS.finditer(text)))
        if matches:
            raise ValueError(f"forbidden model/matcher token in selected implementation {path}: {matches}")
        scans.append({**record(path), "forbidden_token_matches": []})
    return {
        "schema": "pw_d_selected_codepath_commercial_clean_evidence_v1",
        "scope": "selected self-developed D implementation and exact execution harness; no external model weights",
        "jpeg_backend_label": "libjpeg_turbo_product",
        "selected_codepaths": scans,
        "forbidden_tokens": ["LoFTR", "ScanNet", "ONNX", "CoreML", "PyTorch", "TorchScript"],
        "forbidden_token_matches": [],
    }


def validate_inventory(inventory: dict, execution: dict) -> tuple[int, int, list[dict]]:
    total = inventory.get("total_count")
    available = inventory.get("available_count")
    available_inputs = inventory.get("available_inputs")
    missing = inventory.get("missing_inputs")
    if (
        not isinstance(total, int)
        or not isinstance(available, int)
        or not isinstance(available_inputs, list)
        or not isinstance(missing, list)
    ):
        raise ValueError("asset inventory malformed")
    if available != len(available_inputs) or available + len(missing) != total:
        raise ValueError("asset inventory count mismatch")
    available_ids: set[str] = set()
    for item in available_inputs:
        if not isinstance(item, dict) or set(item) != {"id", "path", "sha256"}:
            raise ValueError("available inventory row malformed")
        identity = str(item["id"])
        path = Path(item["path"])
        if identity in available_ids or not path.is_file() or sha256(path) != item["sha256"]:
            raise ValueError(f"available inventory identity/hash mismatch: {identity}")
        available_ids.add(identity)
    missing_ids: set[str] = set()
    for item in missing:
        if not isinstance(item, dict) or set(item) != {"id", "path"}:
            raise ValueError("missing inventory row malformed")
        identity = str(item["id"])
        if identity in missing_ids or identity in available_ids or Path(item["path"]).exists():
            raise ValueError(f"missing inventory identity/path mismatch: {identity}")
        missing_ids.add(identity)
    expected_missing = {str(value) for value in execution.get("missing_registered_jpeg_frame_ids", [])}
    if missing_ids != expected_missing:
        raise ValueError("inventory missing identities differ from exact D execution")
    if inventory.get("coverage_fraction") != available / total:
        raise ValueError("asset inventory coverage fraction mismatch")
    return total, available, missing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture", choices=("cap40", "cap41", "cap50"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument(
        "--implementation-template",
        type=Path,
        default=Path(__file__).resolve().parent / "cap41" / "d_exact_certificate.json",
    )
    args = parser.parse_args()

    run_dir = args.root / args.capture
    source_path = run_dir / "d_exact_certificate.json"
    inventory_path = run_dir / "d_asset_inventory.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if source.get("schema") != "pw_d_exact_final_input_certificate_v1":
        raise ValueError("source exact-D schema mismatch")
    validate_source_status(source)
    if source.get("capture") != args.capture or inventory.get("capture_name") != args.capture:
        raise ValueError("capture identity mismatch")

    execution = source.get("execution")
    parity = execution.get("scheduler_parity") if isinstance(execution, dict) else None
    if not isinstance(parity, dict) or parity.get("exact") is not True:
        raise ValueError("scheduler parity is not exact")
    mismatch_keys = (
        "floor_mask_mismatches",
        "wall_mask_mismatches",
        "structural_mask_mismatches",
        "product_birth_mask_mismatches",
    )
    if any(parity.get(key) != 0 for key in mismatch_keys):
        raise ValueError("scheduler mask parity failed")
    if execution.get("b_structural_conflicts_born_by_d") != 0:
        raise ValueError("D created a B-owned structural birth")

    source_outputs = source.get("outputs") or {}
    replay_source = source_outputs.get("d_replay_gauge") or source_outputs.get("d_replay")
    metric_source = source_outputs.get("d_metric_gauge") or source_outputs.get("d_metric")
    if not isinstance(replay_source, dict) or not isinstance(metric_source, dict):
        raise ValueError("D output records missing")
    replay_path = Path(replay_source["path"])
    metric_path = Path(metric_source["path"])
    validate_record(replay_source, replay_path)
    validate_record(metric_source, metric_path)
    replay_count = ply_point_count(replay_path)
    metric_count = ply_point_count(metric_path)
    validate_output_counts(execution, replay_count, metric_count)

    native = (source.get("inputs") or {}).get("native_library")
    if not isinstance(native, dict):
        raise ValueError("native library identity missing")
    native_path = Path(native["path"])
    validate_record(native, native_path)

    template = json.loads(args.implementation_template.read_text(encoding="utf-8"))
    implementation = template.get("implementation")
    if not isinstance(implementation, dict) or not implementation:
        raise ValueError("implementation identity template missing")
    for raw_path, expected_sha in implementation.items():
        path = Path(raw_path)
        if not path.is_file() or sha256(path) != expected_sha:
            raise ValueError(f"implementation identity changed: {path}")

    harness_path = (
        args.root.parent.parent.parent
        / "detector_free_a16_bench_2026-07-15"
        / "product_exact_input_certificate.dart"
    )
    if not harness_path.is_file():
        raise ValueError(f"exact-D harness absent: {harness_path}")

    execution_path = Path(execution["certificate"]["path"])
    validate_record(execution["certificate"], execution_path)
    execution_document = json.loads(execution_path.read_text(encoding="utf-8"))
    total, available, missing = validate_inventory(inventory, execution)
    completeness = "full" if not missing and available == total else "partial"
    audited_paths = [Path(path) for path in implementation] + [harness_path]
    commercial_evidence = validate_commercial_clean_source(source, execution_document, audited_paths)
    commercial_evidence_path = run_dir / "d_commercial_clean_evidence.json"
    commercial_evidence_path.write_text(
        json.dumps(commercial_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    normalized = dict(source)
    normalized.update(
        {
            "schema": "pw_d_exact_final_input_certificate_v1",
            "status": (
                "PASS_EXACT_D_NEW_FINAL_INPUT"
                if completeness == "full"
                else "PASS_INPUT_EXACT_COMMERCIAL_CLEAN_PARTIAL_ASSETS"
            ),
            "commercial_clean": COMMERCIAL_CLEAN,
            "recomputed_for_final_stack": True,
            "asset_completeness": completeness,
            "asset_inventory": record(inventory_path),
            "source_exact_certificate": record(source_path),
            "implementation": implementation,
            "exact_harness": record(harness_path),
            "commercial_clean_evidence": record(commercial_evidence_path),
            "outputs": {
                **source_outputs,
                "d_replay_gauge": record(replay_path, point_count=replay_count),
                "d_metric_gauge": record(metric_path, point_count=metric_count),
            },
            "inputs": {
                **(source.get("inputs") or {}),
                "native_library": record(native_path),
            },
        }
    )
    output_path = run_dir / "d_exact_certificate_normalized.json"
    output_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output_path), "sha256": sha256(output_path), "births": replay_count}))


if __name__ == "__main__":
    main()
