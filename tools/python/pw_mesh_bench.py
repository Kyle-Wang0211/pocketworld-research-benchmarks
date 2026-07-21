#!/usr/bin/env python3
"""CLI for a controlled FuseCut-vs-TSDF observation-consistency benchmark.

``evaluate-mesh`` is the production path and lazily imports Open3D.
``evaluate-fixture`` is a deterministic analytic/test path that consumes frozen
ray hits.  ``compare`` refuses to emit any gate numbers until both route result
digests match the expected frozen input digest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Iterator, Mapping, Sequence

import numpy as np

import b0_input_contract as C
import mesh_ab_eval as E


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    fixture = commands.add_parser("evaluate-fixture", help="evaluate preregistered ray-hit fixture")
    fixture.add_argument("--frames", type=Path, required=True)
    fixture.add_argument("--hits", type=Path, required=True)
    fixture.add_argument("--topology", type=Path, required=True)
    fixture.add_argument("--contract-digest", required=True)
    fixture.add_argument("--mesh-frame", choices=("contract_model",), required=True)
    fixture.add_argument("--input-contract", type=Path, required=True)
    fixture.add_argument("--split-id", required=True)
    fixture.add_argument("--out", type=Path, required=True)

    mesh = commands.add_parser("evaluate-mesh", help="ray cast one contract-bound mesh")
    mesh.add_argument("--frames", type=Path, required=True)
    mesh.add_argument("--mesh", type=Path, required=True)
    mesh.add_argument(
        "--mesh-frame",
        choices=("contract_model", "alicevision_obj"),
        required=True,
        help="storage encoding only; semantic frame comes from --input-contract",
    )
    mesh.add_argument("--route-provenance", type=Path, required=True)
    mesh.add_argument(
        "--route-monitor-status",
        type=Path,
        required=True,
        help="absolute b0-monitored-command-v1 status that attests this mesh",
    )
    mesh.add_argument("--prepared-provenance", type=Path, required=True)
    mesh.add_argument("--preregistered-contract", type=Path, required=True)
    mesh.add_argument("--input-contract", type=Path, required=True)
    mesh.add_argument("--split-id", required=True)
    mesh.add_argument("--out", type=Path, required=True)

    compare = commands.add_parser("compare", help="compare frozen TSDF and FuseCut evaluations")
    compare.add_argument("--tsdf", type=Path, required=True)
    compare.add_argument("--fusecut", type=Path, required=True)
    compare.add_argument("--frames", type=Path, required=True)
    compare.add_argument("--prepared-provenance", type=Path, required=True)
    compare.add_argument("--preregistered-contract", type=Path, required=True)
    compare.add_argument("--input-contract", type=Path, required=True)
    compare.add_argument("--split-id", required=True)
    compare.add_argument("--bootstrap-replicates", type=int, default=10_000)
    compare.add_argument("--bootstrap-seed", type=int, default=20260721)
    compare.add_argument("--out", type=Path, required=True)
    return parser


def _load_contract_archive(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        missing = [key for key in E.CONTRACT_ARRAY_KEYS if key not in archive.files]
        extra = sorted(set(archive.files) - set(E.CONTRACT_ARRAY_KEYS))
        if missing or extra:
            raise E.EvaluationContractError(
                E.ROUTE_INPUT_NOT_EQUIVALENT,
                f"archive schema mismatch; missing={missing}, extra={extra}",
            )
        arrays = {key: np.asarray(archive[key]) for key in E.CONTRACT_ARRAY_KEYS}
    _validate_contract_shapes(arrays)
    return arrays


def _validate_contract_shapes(arrays: Mapping[str, np.ndarray]) -> None:
    frames = arrays["frames"]
    depth = arrays["depth"]
    if frames.ndim != 1 or frames.dtype.kind not in "SU" or len(set(frames.tolist())) != len(frames):
        raise E.EvaluationContractError(E.ROUTE_INPUT_NOT_EQUIVALENT, "frames must be unique strings")
    if depth.ndim != 3 or not np.issubdtype(depth.dtype, np.floating):
        raise E.EvaluationContractError(E.ROUTE_INPUT_NOT_EQUIVALENT, "depth must be F x H x W float")
    frame_count, height, width = depth.shape
    if len(frames) != frame_count or arrays["K"].shape != (frame_count, 3, 3):
        raise E.EvaluationContractError(E.ROUTE_INPUT_NOT_EQUIVALENT, "frame/K dimensions differ")
    if arrays["w2c"].shape != (frame_count, 4, 4):
        raise E.EvaluationContractError(E.ROUTE_INPUT_NOT_EQUIVALENT, "w2c must be F x 4 x 4")
    for name in ("roi", "low_texture", "weak_support", "planar_single_surface"):
        if arrays[name].shape != (frame_count, height, width) or arrays[name].dtype != np.bool_:
            raise E.EvaluationContractError(
                E.ROUTE_INPUT_NOT_EQUIVALENT, f"{name} must be F x H x W bool"
            )
    finite_camera = np.isfinite(arrays["K"]).all() and np.isfinite(arrays["w2c"]).all()
    if not finite_camera:
        raise E.EvaluationContractError(E.ROUTE_INPUT_NOT_EQUIVALENT, "camera arrays are nonfinite")


def _assert_expected_digest(arrays: Mapping[str, np.ndarray], expected: str) -> str:
    actual = E.frozen_input_digest(arrays)
    if actual != expected:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, f"computed input digest {actual} != expected {expected}"
        )
    return actual


def _route_manifest_digest(provenance: Mapping[str, Any]) -> str:
    """Extract the actual reconstruction-input digest from either route."""

    direct = provenance.get("semantic_manifest_sha256")
    nested = provenance.get("input_equivalence_contract")
    value = direct
    if value is None and isinstance(nested, Mapping):
        value = nested.get("semantic_manifest_sha256")
    if not isinstance(value, str) or len(value) != 64:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "route provenance lacks a semantic_manifest_sha256",
        )
    try:
        bytes.fromhex(value)
    except ValueError as error:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, "route semantic digest is not hexadecimal"
        ) from error
    return value


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, f"{label} is missing or is not an object"
        )
    return value


def _require_hex_digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, f"{label} is not a SHA-256 digest"
        )
    try:
        bytes.fromhex(value)
    except ValueError as error:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, f"{label} is not hexadecimal"
        ) from error
    return value


def _canonical_frame_list_sha256(names: Any, *, label: str) -> str:
    if not isinstance(names, list) or not names:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, f"{label} must be a non-empty array"
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for name in names:
        if (
            not isinstance(name, str)
            or not name
            or name != name.strip()
            or Path(name).name != name
            or name in {".", ".."}
            or name in seen
        ):
            raise E.EvaluationContractError(
                E.ROUTE_INPUT_NOT_EQUIVALENT, f"{label} contains an invalid frame name"
            )
        normalized.append(name)
        seen.add(name)
    return hashlib.sha256(("\n".join(normalized) + "\n").encode("utf-8")).hexdigest()


def _route_frame_list_digest(provenance: Mapping[str, Any]) -> str:
    direct = provenance.get("frame_list_sha256")
    if direct is not None:
        return _require_hex_digest(direct, "route frame-list digest")
    inputs = provenance.get("inputs")
    if isinstance(inputs, Mapping):
        frame_list = inputs.get("frame_list")
        if isinstance(frame_list, Mapping):
            return _require_hex_digest(
                frame_list.get("file_sha256"), "route frame-list digest"
            )
    raise E.EvaluationContractError(
        E.ROUTE_INPUT_NOT_EQUIVALENT, "route provenance lacks a frame-list digest"
    )


def _binding_digest(binding: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(b"pocketworld.b0.evaluation-binding.v1\0" + encoded).hexdigest()


def _heldout_semantic_manifest(arrays: Mapping[str, np.ndarray]) -> str:
    frame_hashes = []
    for index, name in enumerate(np.asarray(arrays["frames"]).tolist()):
        depth = np.asarray(arrays["depth"][index])
        frame_hashes.append(
            C.canonical_frame_semantic_sha256(
                name,
                np.isfinite(depth) & (depth > 0),
                depth,
                np.asarray(arrays["K"][index]),
                np.asarray(arrays["w2c"][index]),
            )
        )
    return C.semantic_manifest_sha256(frame_hashes)


def _same_float(actual: Any, expected: float) -> bool:
    try:
        return float(actual).hex() == float(expected).hex()
    except (TypeError, ValueError):
        return False


def _require_contract_fields(
    candidate: Any, expected: Mapping[str, Any], *, label: str
) -> Mapping[str, Any]:
    value = _require_mapping(candidate, label)
    mismatches: list[str] = []
    for key, wanted in expected.items():
        actual = value.get(key)
        if isinstance(wanted, float):
            matches = _same_float(actual, wanted)
        elif isinstance(wanted, bool):
            matches = actual is wanted
        else:
            matches = actual == wanted
        if not matches:
            mismatches.append(key)
    if mismatches:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            f"{label} differs from the shared input contract at {mismatches}",
        )
    return value


def _validate_experiment_binding(
    *,
    arrays: Mapping[str, np.ndarray],
    frames_path: Path,
    prepared_provenance_path: Path,
    preregistered_contract_path: Path,
    input_contract_path: Path,
    split_id: str,
    route_provenance_path: Path | None,
) -> tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    """Bind quality evaluation to the shared input-contract SSOT.

    Dataset, semantic coordinate frame, physical scale, component identities,
    and split membership are derived exclusively from ``input_contract_path``.
    No CLI field can override them.
    """

    try:
        input_contract, input_contract_sha256 = C.load_input_contract(
            input_contract_path
        )
        selected_split = C.select_input_contract_split(input_contract, split_id)
    except C.RouteInputNotEquivalent as error:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, "input contract or selected split is invalid"
        ) from error

    dataset_id = str(input_contract["dataset_id"])
    coordinate_frame = str(input_contract["coordinate_frame"])
    metres_per_model_unit = float(input_contract["metres_per_model_unit"])
    policy = _require_mapping(
        input_contract["transductive_policy"], "input-contract transductive policy"
    )
    if (
        policy.get("route_allowed") is not True
        or selected_split.get("route_allowed", True) is not True
        or policy.get("quality_scoring_forbidden") is True
        or selected_split.get("quality_scoring_forbidden", False) is True
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            f"quality scoring is forbidden by input-contract split {split_id!r}",
        )

    reconstruction = _require_mapping(
        selected_split.get("reconstruction"), "input-contract reconstruction split"
    )
    heldout = _require_mapping(
        selected_split.get("heldout"), "input-contract heldout split"
    )
    reconstruction_names = list(reconstruction["frames"])
    heldout_names = list(heldout["frames"])
    expected_reconstruction_hash = _require_hex_digest(
        reconstruction.get("file_sha256"), "input-contract reconstruction-list digest"
    )
    expected_heldout_hash = _require_hex_digest(
        heldout.get("file_sha256"), "input-contract heldout-list digest"
    )
    expected_reconstruction_semantic = _require_hex_digest(
        reconstruction.get("semantic_sha256"),
        "input-contract reconstruction ordered semantic digest",
    )
    expected_heldout_semantic = _require_hex_digest(
        heldout.get("semantic_sha256"),
        "input-contract heldout ordered semantic digest",
    )
    expected_dmcache_hash = _require_hex_digest(
        input_contract["dmcache"].get("sha256"), "input-contract dmcache digest"
    )
    expected_model_hash = _require_hex_digest(
        input_contract["model_cache"].get("sha256"),
        "input-contract model-cache digest",
    )
    expected_image_manifest = _require_hex_digest(
        input_contract["images"].get("root_manifest_sha256"),
        "input-contract image manifest digest",
    )

    contract = _require_mapping(
        _load_json(preregistered_contract_path), "preregistered contract"
    )
    if (
        contract.get("schema_version") != "b0-preregistration-v1"
        or contract.get("only_experimental_variable") != "meshing_backend"
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, "preregistration identity is not the B0 mesher-only contract"
        )
    frozen_authority = _require_mapping(
        contract.get("frozen_authority"), "preregistered frozen authority"
    )
    preregistered_input = _require_mapping(
        frozen_authority.get("input_contract"), "preregistered input contract"
    )
    _require_contract_fields(
        preregistered_input,
        {
            "schema_version": C.INPUT_CONTRACT_SCHEMA_VERSION,
            "raw_sha256": input_contract_sha256,
            "dataset_id": dataset_id,
            "split_id": split_id,
            "coordinate_frame": coordinate_frame,
            "metres_per_model_unit": metres_per_model_unit,
            "universe_count": len(input_contract["dmcache"]["frame_order"]),
            "reconstruction_count": len(reconstruction_names),
            "heldout_count": len(heldout_names),
        },
        label="preregistered input-contract identity",
    )
    if (
        contract.get("dataset_id") != dataset_id
        or contract.get("input_split_id") != split_id
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "preregistration dataset/split differs from the input contract",
        )
    frozen_data = _require_mapping(
        frozen_authority.get("data_sha256"), "preregistered frozen data hashes"
    )
    _require_contract_fields(
        frozen_data,
        {
            "dmcache": expected_dmcache_hash,
            "model_cache": expected_model_hash,
            "images_root_manifest": expected_image_manifest,
        },
        label="preregistered frozen data hashes",
    )
    splits = _require_mapping(contract.get("splits"), "preregistered splits")
    split = _require_mapping(splits.get(dataset_id), f"split {dataset_id!r}")
    execution_plan = _require_mapping(
        contract.get("execution_plan"), "preregistered execution plan"
    )
    execution_entry = execution_plan.get(dataset_id, {})
    if split.get("quality_claim_allowed") is False or (
        isinstance(execution_entry, Mapping)
        and execution_entry.get("quality_scoring_forbidden") is True
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            f"quality scoring is forbidden for dataset_id {dataset_id!r}",
        )
    list_hashes = _require_mapping(split.get("list_sha256"), "split list hashes")
    _require_contract_fields(
        split,
        {
            "source_input_contract_split_id": split_id,
            "reconstruction_count": len(reconstruction_names),
            "heldout_count": len(heldout_names),
            "quality_claim_allowed": True,
        },
        label="preregistered selected split",
    )
    _require_contract_fields(
        list_hashes,
        {
            "reconstruction": expected_reconstruction_hash,
            "heldout": expected_heldout_hash,
        },
        label="preregistered split list hashes",
    )
    if not isinstance(execution_entry, Mapping) or (
        execution_entry.get("input_contract_split_id") != split_id
        or execution_entry.get("quality_scoring_forbidden") is not False
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "preregistered execution entry differs from selected input split",
        )

    gates = _require_mapping(contract.get("gates"), "preregistered gates")
    # The prompt's B0.6 strict profile is authoritative for both quality
    # cohorts.  A relaxed small-cohort profile is never selected.
    gate_contract_key = (
        "b0_prompt_strict" if "b0_prompt_strict" in gates else "full413_strict"
    )
    gate_contract = _require_mapping(
        gates.get(gate_contract_key), "strict B0.6 gate contract"
    )
    E.preregistered_gate_profile(dataset_id, gate_contract)
    improvement_contract = _require_mapping(
        contract.get("improvement_claim"), "preregistered improvement claim"
    )
    E.preregistered_improvement_claim(improvement_contract)

    prepared = _require_mapping(
        _load_json(prepared_provenance_path), "prepared input provenance"
    )
    if (
        prepared.get("schema_version") != "b0-prepared-evaluation-provenance-v1"
        or prepared.get("artifact_schema_version") != "b0-prepared-evaluation-v1"
        or prepared.get("input_only") is not True
        or prepared.get("mesh_inputs_accepted") is not False
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, "prepared input provenance has the wrong schema or boundary"
        )
    prepared_dataset_id = prepared.get("dataset_id")
    if (
        prepared_dataset_id != dataset_id
        or prepared.get("split_id") != split_id
        or prepared.get("split_profile") != split_id
        or prepared.get("route_allowed") is not True
        or prepared.get("quality_scoring_forbidden") is not False
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "prepared provenance dataset/split gates differ from the input contract",
        )
    prepared_split_profile = prepared.get("split_profile")
    if not isinstance(prepared_split_profile, str) or not prepared_split_profile:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, "prepared split profile is missing"
        )

    split_binding = _require_mapping(
        prepared.get("split_binding"), "prepared split binding"
    )
    _require_contract_fields(
        split_binding,
        {
            "dataset_id": dataset_id,
            "split_id": split_id,
            "route_allowed": True,
            "quality_scoring_forbidden": False,
            "reconstruction_file_sha256": expected_reconstruction_hash,
            "heldout_file_sha256": expected_heldout_hash,
            "reconstruction_ordered_semantic_sha256": expected_reconstruction_semantic,
            "heldout_ordered_semantic_sha256": expected_heldout_semantic,
        },
        label="prepared split binding",
    )

    actual_frames = np.asarray(arrays["frames"]).tolist()
    heldout_hash = _canonical_frame_list_sha256(
        actual_frames, label="prepared heldout frame order"
    )
    if (
        actual_frames != heldout_names
        or heldout_hash != expected_heldout_semantic
        or prepared.get("frame_order") != actual_frames
        or prepared.get("frame_count") != len(actual_frames)
        or len(actual_frames) != len(heldout_names)
        or prepared.get("shape") != list(np.asarray(arrays["depth"]).shape)
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "prepared archive frame order/count/shape does not match the selected split",
        )

    components = _require_mapping(
        prepared.get("component_sha256"), "prepared component hashes"
    )
    preparation_source = Path(__file__).with_name("b0_prepare_eval.py").resolve()
    if (
        components.get("reconstruction_list") != expected_reconstruction_hash
        or components.get("heldout_list") != expected_heldout_hash
        or components.get("dmcache") != expected_dmcache_hash
        or components.get("model_cache") != expected_model_hash
        or components.get("input_contract") != input_contract_sha256
        or components.get("registered_image_root_manifest") != expected_image_manifest
        or components.get("output_npz") != _sha256_file(frames_path)
        or components.get("mesh_ab_eval.py") != _sha256_file(Path(E.__file__).resolve())
        or components.get("b0_prepare_eval.py") != _sha256_file(preparation_source)
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "prepared archive/list/evaluator component hashes differ from the freeze",
        )
    evaluation_digest = E.frozen_input_digest(arrays)
    if not (
        prepared.get("evaluator_digest")
        == evaluation_digest
        == prepared.get("evaluation_digest")
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, "prepared evaluator/archive digest differs from the freeze"
        )
    semantics = _require_mapping(
        prepared.get("semantic_manifest_sha256"), "prepared semantic manifests"
    )
    route_semantic_digest = _require_hex_digest(
        semantics.get("reconstruction"), "prepared reconstruction semantic digest"
    )
    heldout_semantic_digest = _require_hex_digest(
        semantics.get("heldout"), "prepared heldout semantic digest"
    )
    if heldout_semantic_digest != _heldout_semantic_manifest(arrays):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "prepared heldout semantic digest is not derivable from the archive",
        )
    coordinate_scale = _require_mapping(
        prepared.get("coordinate_scale"), "prepared coordinate scale"
    )
    if (
        coordinate_scale.get("stored_coordinate_frame") != coordinate_frame
        or coordinate_scale.get("contract_coordinate_frame") != coordinate_frame
        or coordinate_scale.get("stored_arrays_rescaled") is not False
        or coordinate_scale.get("absolute_threshold_conversion")
        != "model_units = metres / metres_per_model_unit"
    ):
        raise E.EvaluationContractError(
            E.COORDINATE_FRAME_MISMATCH,
            "prepared archive is not in the input-contract coordinate frame",
        )
    if not _same_float(
        coordinate_scale.get("metres_per_model_unit"), metres_per_model_unit
    ):
        raise E.EvaluationContractError(
            E.COORDINATE_FRAME_MISMATCH, "prepared metric scale differs from input contract"
        )
    if coordinate_frame != "raw_lapa_model" and any(
        key in coordinate_scale
        for key in ("metres_per_raw_lapa_unit", "frozen_sim3_sha256")
    ):
        raise E.EvaluationContractError(
            E.COORDINATE_FRAME_MISMATCH,
            "non-LAPA prepared data carries an unrelated LAPA transform",
        )

    if route_provenance_path is not None:
        route = _require_mapping(_load_json(route_provenance_path), "route provenance")
        route_order = route.get("frame_order")
        frozen_input = _require_mapping(
            route.get("frozen_input_identity_contract"),
            "route frozen input identity contract",
        )
        validated_fields = _require_mapping(
            frozen_input.get("validated_fields"),
            "route frozen input validated fields",
        )
        expected_validated_fields = {
            "dataset_id": dataset_id,
            "coordinate_frame": coordinate_frame,
            "metres_per_model_unit": metres_per_model_unit,
            "transductive_policy": dict(policy),
            "dmcache_frame_order_sha256": input_contract["dmcache"][
                "frame_order_sha256"
            ],
            "model_cache_frame_order_sha256": input_contract["model_cache"][
                "frame_order_sha256"
            ],
            "reconstruction_file_sha256": expected_reconstruction_hash,
            "reconstruction_semantic_sha256": expected_reconstruction_semantic,
            "heldout_file_sha256": expected_heldout_hash,
            "heldout_semantic_sha256": expected_heldout_semantic,
            "image_root_manifest_sha256": expected_image_manifest,
        }
        _require_contract_fields(
            frozen_input,
            {
                "sha256": input_contract_sha256,
                "schema_version": C.INPUT_CONTRACT_SCHEMA_VERSION,
                "split_id": split_id,
            },
            label="route frozen input identity",
        )
        _require_contract_fields(
            validated_fields,
            expected_validated_fields,
            label="route frozen input validated fields",
        )
        route_split_id = route.get("split_id")
        if (
            route.get("dataset_id") != dataset_id
            or route.get("coordinate_frame") != coordinate_frame
            or not _same_float(route.get("metres_per_model_unit"), metres_per_model_unit)
            or (route_split_id is not None and route_split_id != split_id)
            or route.get("dmcache_sha256") != expected_dmcache_hash
            or route.get("model_cache_sha256") != expected_model_hash
            or _route_manifest_digest(route) != route_semantic_digest
            or _route_frame_list_digest(route) != expected_reconstruction_hash
            or route.get("frame_count") != len(reconstruction_names)
            or route_order != reconstruction_names
            or _canonical_frame_list_sha256(
                route_order, label="route reconstruction frame order"
            )
            != expected_reconstruction_semantic
        ):
            raise E.EvaluationContractError(
                E.ROUTE_INPUT_NOT_EQUIVALENT,
                "route provenance differs from the selected reconstruction split",
            )
        transform = route.get("coordinate_transform")
        if transform is not None:
            _require_contract_fields(
                transform,
                {
                    "mesh_output": coordinate_frame,
                    "metres_per_model_unit": metres_per_model_unit,
                    "transform_applied_by_route": False,
                    "sim3_applied_to_mesh": False,
                    "icp_applied_to_mesh": False,
                },
                label="route coordinate transform",
            )
        elif route.get("schema") == "pocketworld.b0.tsdf.provenance.v2":
            raise E.EvaluationContractError(
                E.COORDINATE_FRAME_MISMATCH,
                "TSDF provenance lacks its no-transform mesh declaration",
            )
        legacy_sim3 = route.get("frozen_sim3_model_to_arkit")
        if legacy_sim3 is not None:
            sim3 = _require_mapping(legacy_sim3, "route frozen Sim(3) semantics")
            if (
                sim3.get("applied_by_adapter") is not False
                or sim3.get("applicable") is not (
                    coordinate_frame == "raw_lapa_model"
                )
                or sim3.get("canonical_sha256") != E.FROZEN_SIM3_SHA256
            ):
                raise E.EvaluationContractError(
                    E.COORDINATE_FRAME_MISMATCH,
                    "route Sim(3) semantics conflict with the contract model frame",
                )

    binding: dict[str, Any] = {
        "schema": "pocketworld.b0.evaluation-binding.v1",
        "dataset_id": dataset_id,
        "split_id": split_id,
        "prepared_split_profile": prepared_split_profile,
        "only_experimental_variable": "meshing_backend",
        "coordinate_frame": coordinate_frame,
        "metres_per_model_unit": metres_per_model_unit,
        "input_contract_path": str(input_contract_path.resolve()),
        "input_contract_sha256": input_contract_sha256,
        "input_contract_schema_version": C.INPUT_CONTRACT_SCHEMA_VERSION,
        "preregistered_contract_path": str(preregistered_contract_path.resolve()),
        "preregistered_contract_sha256": _sha256_file(preregistered_contract_path),
        "prepared_provenance_path": str(prepared_provenance_path.resolve()),
        "prepared_provenance_sha256": _sha256_file(prepared_provenance_path),
        "prepared_archive_path": str(frames_path.resolve()),
        "prepared_archive_sha256": _sha256_file(frames_path),
        "dmcache_sha256": expected_dmcache_hash,
        "model_cache_sha256": expected_model_hash,
        "reconstruction_list_sha256": expected_reconstruction_hash,
        "heldout_list_sha256": expected_heldout_hash,
        "reconstruction_ordered_semantic_sha256": expected_reconstruction_semantic,
        "heldout_ordered_semantic_sha256": expected_heldout_semantic,
        "reconstruction_frame_count": len(reconstruction_names),
        "heldout_frame_count": len(heldout_names),
        "route_semantic_manifest_sha256": route_semantic_digest,
        "heldout_semantic_manifest_sha256": heldout_semantic_digest,
        "evaluation_digest": evaluation_digest,
        "evaluator_source_sha256": _sha256_file(Path(E.__file__).resolve()),
        "preparation_source_sha256": _sha256_file(preparation_source),
        "gate_contract_key": gate_contract_key,
        "bootstrap_replicates": E.FINAL_BOOTSTRAP_REPLICATES,
        "bootstrap_seed": E.FINAL_BOOTSTRAP_SEED,
    }
    binding["binding_sha256"] = _binding_digest(binding)
    return binding, gate_contract, improvement_contract


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _stable_file_identity(path: Path, *, label: str) -> tuple[int, str]:
    if not path.is_absolute() or path.resolve() != path or path.is_symlink():
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            f"{label} must be an absolute canonical non-symlink path",
        )
    try:
        before = path.stat()
        if not path.is_file() or before.st_size <= 0:
            raise OSError("not a nonempty regular file")
        digest = _sha256_file(path)
        after = path.stat()
    except OSError as error:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, f"{label} is unreadable: {path}"
        ) from error
    before_identity = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    )
    after_identity = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    )
    if before_identity != after_identity:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, f"{label} changed while being hashed"
        )
    return after.st_size, digest


def _route_phase(route: Mapping[str, Any]) -> str:
    schema = route.get("schema")
    if schema == "pocketworld.b0.tsdf.provenance.v2":
        return "tsdf_meshing"
    if schema == "pocketworld-b0-alicevision-export-v1":
        return "fusecut_meshing"
    raise E.EvaluationContractError(
        E.ROUTE_INPUT_NOT_EQUIVALENT,
        f"unsupported route provenance schema for monitor binding: {schema!r}",
    )


def _validate_route_monitor_status(
    *,
    mesh_path: Path,
    monitor_status_path: Path,
    route_provenance_path: Path,
    preregistered_contract_path: Path,
) -> dict[str, Any]:
    """Bind a mesh to the exact PASSing formal command that produced it."""

    mesh_size, mesh_sha256 = _stable_file_identity(mesh_path, label="route mesh")
    status_size, status_sha256 = _stable_file_identity(
        monitor_status_path, label="route monitor status"
    )
    route = _require_mapping(_load_json(route_provenance_path), "route provenance")
    contract = _require_mapping(
        _load_json(preregistered_contract_path), "preregistered contract"
    )
    status = _require_mapping(
        _load_json(monitor_status_path), "route monitor status"
    )
    phase = _route_phase(route)

    execution_plan = _require_mapping(
        contract.get("execution_plan"), "preregistered execution plan"
    )
    runner_bindings = _require_mapping(
        execution_plan.get("formal_runner_bindings"),
        "preregistered formal runner bindings",
    )
    phase_binding = _require_mapping(
        runner_bindings.get(phase), f"preregistered formal phase {phase!r}"
    )
    expected_argv = phase_binding.get("child_argv")
    expected_argv_sha256 = phase_binding.get("child_argv_sha256")
    if (
        not isinstance(expected_argv, list)
        or not expected_argv
        or any(not isinstance(item, str) for item in expected_argv)
        or _canonical_json_sha256(expected_argv) != expected_argv_sha256
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            f"preregistered formal phase {phase!r} argv identity is invalid",
        )

    authority = _require_mapping(
        contract.get("frozen_authority"), "preregistered frozen authority"
    )
    source_state = _require_mapping(
        authority.get("source_state"), "preregistered source state"
    )
    source_bundle = _require_mapping(
        source_state.get("dirty_code_bundle"), "preregistered dirty code bundle"
    )
    alicevision_binary = _require_mapping(
        authority.get("alicevision_binary"), "preregistered AliceVision binary"
    )
    environment = _require_mapping(
        authority.get("environment_identity"), "preregistered environment identity"
    )
    formal = _require_mapping(status.get("formal_binding"), "monitor formal binding")
    expected_contract_path = preregistered_contract_path.resolve()
    expected_contract_sha256 = _sha256_file(expected_contract_path)
    _require_contract_fields(
        formal,
        {
            "status": "VERIFIED",
            "contract_path": str(expected_contract_path),
            "contract_sha256": expected_contract_sha256,
            "phase": phase,
            "child_argv_sha256": expected_argv_sha256,
            "source_bundle_sha256": source_bundle.get("bundle_sha256"),
            "alicevision_binary_sha256": alicevision_binary.get("sha256"),
            "environment_sha256": environment.get("sha256"),
        },
        label="monitor formal binding",
    )
    command = _require_mapping(status.get("command"), "monitor command")
    if (
        command.get("argv") != expected_argv
        or command.get("canonical_sha256") != expected_argv_sha256
        or command.get("shell") is not False
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "monitor command differs from the preregistered formal child argv",
        )
    if phase == "fusecut_meshing" and expected_argv[0] != alicevision_binary.get(
        "path"
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "FuseCut monitor command does not invoke the frozen AliceVision binary",
        )
    if (
        status.get("schema_version") != "b0-monitored-command-v1"
        or status.get("verdict") != "PASS"
        or status.get("command_outcome") != "SUCCESS"
        or status.get("started") is not True
        or status.get("exit_code") != 0
        or status.get("launch_error") is not None
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "route monitor did not record one successful PASSing formal command",
        )

    attestation = _require_mapping(
        status.get("attestation"), "monitor output attestation"
    )
    files = attestation.get("files")
    if attestation.get("status") != "VERIFIED" or not isinstance(files, list):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "route monitor output attestation is not VERIFIED",
        )
    matching = [
        entry
        for entry in files
        if isinstance(entry, Mapping) and entry.get("path") == str(mesh_path)
    ]
    if len(matching) != 1:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "route monitor does not contain exactly one attestation for the supplied mesh",
        )
    attested_mesh = matching[0]
    if (
        attested_mesh.get("size_bytes") != mesh_size
        or attested_mesh.get("sha256") != mesh_sha256
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "current mesh size/SHA-256 differs from the monitor attestation",
        )

    if phase == "tsdf_meshing":
        route_mesh = _require_mapping(route.get("mesh"), "TSDF route mesh identity")
        route_mesh_path_value = route_mesh.get("path")
        if not isinstance(route_mesh_path_value, str) or not route_mesh_path_value:
            raise E.EvaluationContractError(
                E.ROUTE_INPUT_NOT_EQUIVALENT, "TSDF route mesh path is missing"
            )
        route_mesh_path = Path(route_mesh_path_value)
        if not route_mesh_path.is_absolute():
            route_mesh_path = route_provenance_path.parent / route_mesh_path
        if (
            route_mesh_path.resolve() != mesh_path
            or route_mesh.get("bytes") != mesh_size
            or route_mesh.get("sha256") != mesh_sha256
        ):
            raise E.EvaluationContractError(
                E.ROUTE_INPUT_NOT_EQUIVALENT,
                "TSDF provenance mesh identity differs from monitor/current mesh",
            )

    return {
        "status_path": str(monitor_status_path),
        "status_size_bytes": status_size,
        "status_sha256": status_sha256,
        "schema_version": "b0-monitored-command-v1",
        "verdict": "PASS",
        "phase": phase,
        "formal_contract_path": str(expected_contract_path),
        "formal_contract_sha256": expected_contract_sha256,
        "child_argv_sha256": expected_argv_sha256,
        "source_bundle_sha256": source_bundle.get("bundle_sha256"),
        "alicevision_binary_sha256": alicevision_binary.get("sha256"),
        "environment_sha256": environment.get("sha256"),
        "attested_mesh": {
            "path": str(mesh_path),
            "size_bytes": mesh_size,
            "sha256": mesh_sha256,
        },
    }


def _revalidate_result_monitor_identity(
    result: Mapping[str, Any],
    *,
    binding: Mapping[str, Any],
    preregistered_contract_path: Path,
    expected_phase: str,
    label: str,
) -> Mapping[str, Any]:
    identity = _require_mapping(
        result.get("route_monitor_status"), f"{label} route monitor identity"
    )
    status_path_value = identity.get("status_path")
    if not isinstance(status_path_value, str):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, f"{label} monitor status path is invalid"
        )
    attested_mesh = _require_mapping(
        identity.get("attested_mesh"), f"{label} attested mesh"
    )
    mesh_path_value = attested_mesh.get("path")
    if not isinstance(mesh_path_value, str):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, f"{label} attested mesh path is invalid"
        )
    mesh_path = Path(mesh_path_value)
    mesh_size, mesh_sha256 = _stable_file_identity(
        mesh_path, label=f"{label} attested mesh"
    )
    if (
        attested_mesh.get("size_bytes") != mesh_size
        or attested_mesh.get("sha256") != mesh_sha256
        or result.get("mesh_path") != str(mesh_path)
        or result.get("mesh_size_bytes") != mesh_size
        or result.get("mesh_sha256") != mesh_sha256
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            f"{label} result mesh differs from its monitor identity",
        )
    provenance_path_value = result.get("route_provenance_path")
    if not isinstance(provenance_path_value, str):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            f"{label} route provenance path is invalid",
        )
    provenance_path = Path(provenance_path_value)
    _provenance_size, provenance_sha256 = _stable_file_identity(
        provenance_path, label=f"{label} route provenance"
    )
    if result.get("route_provenance_sha256") != provenance_sha256:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            f"{label} route provenance changed after evaluation",
        )
    current_identity = _validate_route_monitor_status(
        mesh_path=mesh_path,
        monitor_status_path=Path(status_path_value),
        route_provenance_path=provenance_path,
        preregistered_contract_path=preregistered_contract_path,
    )
    if current_identity.get("phase") != expected_phase or dict(identity) != current_identity:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            f"{label} embedded monitor identity differs from current formal evidence",
        )
    return current_identity


def _write_new_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _fixture_sparse_intersections(
    depth_values: Any,
    normal_values: Any,
    *,
    frame_index: int,
    ray_count: int,
    selected_ids: np.ndarray,
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Select only planar fixture rays; never materialize empty per-ray arrays."""

    selected = np.asarray(selected_ids, dtype=np.int64)
    if not len(selected):
        return {}
    if np.any((selected < 0) | (selected >= ray_count)):
        raise ValueError("selected fixture ray is out of bounds")
    frame_depths = np.asarray(depth_values[frame_index])
    frame_normals = np.asarray(normal_values[frame_index])
    try:
        numeric_depths = np.asarray(frame_depths, dtype=np.float64).reshape(ray_count, -1)
        numeric_normals = np.asarray(frame_normals, dtype=np.float64).reshape(
            ray_count, -1, 3
        )
        return {
            int(index): (numeric_depths[index], numeric_normals[index])
            for index in selected
        }
    except (TypeError, ValueError):
        depth_objects = np.asarray(frame_depths, dtype=object).reshape(ray_count)
        normal_objects = np.asarray(frame_normals, dtype=object).reshape(ray_count)
        output: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        for index in selected:
            output[int(index)] = (
                np.asarray(depth_objects[index], dtype=np.float64).reshape(-1),
                np.asarray(normal_objects[index], dtype=np.float64).reshape(-1, 3),
            )
        return output


def _evaluate_hits(
    arrays: Mapping[str, np.ndarray],
    hit_depths: np.ndarray,
    hit_normals: np.ndarray,
    all_intersections: Any,
    all_intersection_normals: Any | None,
    *,
    metres_per_model_unit: float,
) -> dict[str, Any]:
    if hit_depths.shape != arrays["depth"].shape:
        raise ValueError("hit_z shape differs from frozen depth")
    if hit_normals.shape != arrays["depth"].shape + (3,):
        raise ValueError("hit_normals shape differs from frozen depth")
    frame_results = []
    for index in range(len(arrays["frames"])):
        z = arrays["depth"][index]
        masks = {
            "roi": arrays["roi"][index],
            "low_texture": arrays["low_texture"][index],
            "weak_support": arrays["weak_support"][index],
        }
        result = E.evaluate_frame_observations(
            z,
            hit_depths[index],
            masks=masks,
            K=arrays["K"][index],
            hit_normals=hit_normals[index],
            metres_per_model_unit=metres_per_model_unit,
        )
        selected_ids = np.flatnonzero(
            arrays["planar_single_surface"][index].reshape(-1)
        )
        if all_intersection_normals is None:
            sparse = all_intersections[index]
            if not isinstance(sparse, Mapping):
                raise ValueError("sparse multi-hit frame must be a mapping")
        else:
            sparse = _fixture_sparse_intersections(
                all_intersections,
                all_intersection_normals,
                frame_index=index,
                ray_count=z.size,
                selected_ids=selected_ids,
            )
        result["double_shell"] = E.double_shell_metrics(
            observed_z=z.reshape(-1),
            eligible_mask=arrays["planar_single_surface"][index].reshape(-1),
            sparse_intersections=sparse,
            metres_per_model_unit=metres_per_model_unit,
        )
        frame_results.append(result)
    return E.aggregate_frame_results(frame_results)


def _fixture_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    arrays = _load_contract_archive(args.frames)
    digest = _assert_expected_digest(arrays, args.contract_digest)
    if args.mesh_frame != "contract_model":
        raise E.EvaluationContractError(
            E.COORDINATE_FRAME_MISMATCH,
            "ray-hit fixtures must already be in the contract model frame",
        )
    try:
        input_contract, input_contract_sha256 = C.load_input_contract(
            args.input_contract
        )
        C.select_input_contract_split(input_contract, args.split_id)
    except C.RouteInputNotEquivalent as error:
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT, "fixture input contract is invalid"
        ) from error
    coordinate_frame = str(input_contract["coordinate_frame"])
    metres_per_model_unit = float(input_contract["metres_per_model_unit"])
    with np.load(args.hits, allow_pickle=True) as hits:
        required = ("hit_z", "hit_normals", "intersections_z", "intersection_normals")
        missing = [name for name in required if name not in hits.files]
        if missing:
            raise ValueError(f"hit fixture missing {missing}")
        aggregate = _evaluate_hits(
            arrays,
            np.asarray(hits["hit_z"], dtype=np.float64),
            np.asarray(hits["hit_normals"], dtype=np.float64),
            np.asarray(hits["intersections_z"], dtype=object),
            np.asarray(hits["intersection_normals"], dtype=object),
            metres_per_model_unit=metres_per_model_unit,
        )
    topology = _load_json(args.topology)
    return {
        "schema": "pocketworld.mesh-ab.route-evaluation.v1",
        "contract_digest": digest,
        "evaluation_digest": digest,
        "dataset_id": input_contract["dataset_id"],
        "split_id": args.split_id,
        "coordinate_frame": coordinate_frame,
        "mesh_frame": coordinate_frame,
        "source_mesh_frame": "contract_model",
        "metric_scale": "contract_model_units",
        "unit_contract": E.metric_unit_contract(
            coordinate_frame=coordinate_frame,
            metres_per_model_unit=metres_per_model_unit,
            input_contract_sha256=input_contract_sha256,
            split_id=args.split_id,
        ),
        "alignment": "none",
        "observation_semantics": "camera_z",
        "metrics": aggregate["metrics"],
        "frame_counts": aggregate["frame_counts"],
        "topology": topology,
        "limitations": ["observation_consistency_not_ground_truth"],
    }


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _camera_rays(K: np.ndarray, w2c: np.ndarray, shape: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
    height, width = shape
    yy, xx = np.indices((height, width), dtype=np.float64)
    directions_camera = np.stack(
        (
            (xx - K[0, 2]) / K[0, 0],
            (yy - K[1, 2]) / K[1, 1],
            np.ones_like(xx),
        ),
        axis=-1,
    ).reshape(-1, 3)
    c2w = np.linalg.inv(w2c)
    directions_world = directions_camera @ c2w[:3, :3].T
    origins = np.repeat(c2w[None, :3, 3], len(directions_world), axis=0)
    rays = np.concatenate((origins, directions_world), axis=1).astype(np.float32)
    return rays, directions_camera


def _group_listed_intersections(
    *,
    local_ray_ids: np.ndarray,
    listed_z: np.ndarray,
    listed_normals_camera: np.ndarray,
    selected_ids: np.ndarray,
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    """Group multi-hits in O(I log I), without one O(I) mask per ray."""

    ray_ids = np.asarray(local_ray_ids, dtype=np.int64).reshape(-1)
    depths = np.asarray(listed_z, dtype=np.float64).reshape(-1)
    normals = np.asarray(listed_normals_camera, dtype=np.float64).reshape(-1, 3)
    selected = np.asarray(selected_ids, dtype=np.int64).reshape(-1)
    if not (len(ray_ids) == len(depths) == len(normals)):
        raise ValueError("listed intersection arrays differ in length")
    if not len(ray_ids):
        return {}
    if np.any((ray_ids < 0) | (ray_ids >= len(selected))):
        raise ValueError("listed local ray id is out of bounds")
    order = np.lexsort((depths, ray_ids))
    sorted_ids = ray_ids[order]
    sorted_depths = depths[order]
    sorted_normals = normals[order]
    starts = np.concatenate(
        (np.array([0], dtype=np.int64), np.flatnonzero(np.diff(sorted_ids)) + 1)
    )
    ends = np.concatenate((starts[1:], np.array([len(sorted_ids)], dtype=np.int64)))
    output: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for start, end in zip(starts.tolist(), ends.tolist(), strict=True):
        local_id = int(sorted_ids[start])
        output[int(selected[local_id])] = (
            sorted_depths[start:end].astype(np.float32, copy=True),
            sorted_normals[start:end].astype(np.float32, copy=True),
        )
    return output


def _raycast_mesh(
    arrays: Mapping[str, np.ndarray], vertices: np.ndarray, faces: np.ndarray
) -> Iterator[
    tuple[int, np.ndarray, np.ndarray, dict[int, tuple[np.ndarray, np.ndarray]]]
]:
    """Yield one frame at a time so full-run multi-hits are never retained."""

    # Deliberately lazy: analytic tests, comparison, and imports need no Open3D.
    import open3d as o3d  # type: ignore

    legacy = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(vertices), o3d.utility.Vector3iVector(faces.astype(np.int32))
    )
    legacy.compute_triangle_normals()
    triangle_normals_world = np.asarray(legacy.triangle_normals, dtype=np.float64)
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(legacy))
    frame_count, height, width = arrays["depth"].shape
    for frame_index in range(frame_count):
        rays, directions_camera = _camera_rays(
            arrays["K"][frame_index], arrays["w2c"][frame_index], (height, width)
        )
        cast = scene.cast_rays(o3d.core.Tensor(rays))
        t_hit = cast["t_hit"].numpy().astype(np.float64)
        normals_world = cast["primitive_normals"].numpy().astype(np.float64)
        frame_hit_z = E.ray_parameter_to_camera_z(
            t_hit, directions_camera
        ).reshape(height, width).astype(np.float32)
        normals_camera = normals_world @ arrays["w2c"][frame_index, :3, :3].T
        frame_hit_normals = normals_camera.reshape(height, width, 3).astype(np.float32)

        planar = arrays["planar_single_surface"][frame_index].reshape(-1)
        observed = arrays["depth"][frame_index].reshape(-1)
        selected_ids = np.flatnonzero(planar & np.isfinite(observed) & (observed > 0))
        if not len(selected_ids):
            yield frame_index, frame_hit_z, frame_hit_normals, {}
            continue
        listed = scene.list_intersections(o3d.core.Tensor(rays[selected_ids]))
        local_ray_ids = listed["ray_ids"].numpy().astype(np.int64)
        listed_t = listed["t_hit"].numpy().astype(np.float64)
        primitive_ids = listed["primitive_ids"].numpy().astype(np.int64)
        listed_normals_world = triangle_normals_world[primitive_ids]
        listed_normals_camera = listed_normals_world @ arrays["w2c"][frame_index, :3, :3].T
        listed_directions_camera = directions_camera[selected_ids[local_ray_ids]]
        # Preserve signed winding for the multi-hit diagnostic.  Orienting all
        # hits toward the camera would turn the entry/exit faces of a normal
        # closed thin box into a false same-facing duplicate shell.
        listed_z = E.ray_parameter_to_camera_z(listed_t, listed_directions_camera)
        frame_intersections = _group_listed_intersections(
            local_ray_ids=local_ray_ids,
            listed_z=listed_z,
            listed_normals_camera=listed_normals_camera,
            selected_ids=selected_ids,
        )
        yield frame_index, frame_hit_z, frame_hit_normals, frame_intersections


def _mesh_evaluation(args: argparse.Namespace) -> dict[str, Any]:
    arrays = _load_contract_archive(args.frames)
    binding, _, _ = _validate_experiment_binding(
        arrays=arrays,
        frames_path=args.frames,
        prepared_provenance_path=args.prepared_provenance,
        preregistered_contract_path=args.preregistered_contract,
        input_contract_path=args.input_contract,
        split_id=args.split_id,
        route_provenance_path=args.route_provenance,
    )
    evaluation_digest = binding["evaluation_digest"]
    route_digest = binding["route_semantic_manifest_sha256"]
    coordinate_frame = binding["coordinate_frame"]
    metres_per_model_unit = float(binding["metres_per_model_unit"])
    route_monitor_status = _validate_route_monitor_status(
        mesh_path=args.mesh,
        monitor_status_path=args.route_monitor_status,
        route_provenance_path=args.route_provenance,
        preregistered_contract_path=args.preregistered_contract,
    )
    import open3d as o3d  # type: ignore

    loaded = o3d.io.read_triangle_mesh(str(args.mesh), enable_post_processing=False)
    source_vertices = np.asarray(loaded.vertices)
    faces = np.asarray(loaded.triangles)
    vertices = E.vertices_to_contract_model(source_vertices, args.mesh_frame)
    topology = E.mesh_topology_metrics(vertices, faces)
    fatal_reasons = sorted(set(topology["degenerate_reasons"]) - {"zero_area"})
    if fatal_reasons or not topology["finite"]:
        raise E.EvaluationContractError(E.METRIC_UNDEFINED, str(fatal_reasons))
    faces, evaluation_face_filter = E.sanitize_evaluation_faces(vertices, faces)
    def evaluated_frames() -> Iterator[dict[str, Any]]:
        for frame_index, hit_z, hit_normals, sparse_intersections in _raycast_mesh(
            arrays, vertices, faces
        ):
            z = arrays["depth"][frame_index]
            result = E.evaluate_frame_observations(
                z,
                hit_z,
                masks={
                    "roi": arrays["roi"][frame_index],
                    "low_texture": arrays["low_texture"][frame_index],
                    "weak_support": arrays["weak_support"][frame_index],
                },
                K=arrays["K"][frame_index],
                hit_normals=hit_normals,
                metres_per_model_unit=metres_per_model_unit,
            )
            result["double_shell"] = E.double_shell_metrics(
                observed_z=z.reshape(-1),
                eligible_mask=arrays["planar_single_surface"][frame_index].reshape(-1),
                sparse_intersections=sparse_intersections,
                metres_per_model_unit=metres_per_model_unit,
            )
            yield result

    aggregate = E.aggregate_frame_results(evaluated_frames())
    return {
        "schema": "pocketworld.mesh-ab.route-evaluation.v1",
        "contract_digest": route_digest,
        "evaluation_digest": evaluation_digest,
        "dataset_id": binding["dataset_id"],
        "split_id": args.split_id,
        "experiment_binding": binding,
        "coordinate_frame": coordinate_frame,
        "mesh_frame": coordinate_frame,
        "source_mesh_frame": args.mesh_frame,
        "storage_to_contract_rotation": (
            [[1, 0, 0], [0, -1, 0], [0, 0, -1]] if args.mesh_frame == "alicevision_obj" else None
        ),
        "metric_scale": "contract_model_units",
        "unit_contract": E.metric_unit_contract(
            coordinate_frame=coordinate_frame,
            metres_per_model_unit=metres_per_model_unit,
            input_contract_sha256=binding["input_contract_sha256"],
            split_id=args.split_id,
        ),
        "alignment": "none",
        "geometry_transform": {
            "storage_convention_conversion": (
                "alicevision_obj_fixed_diag_1_minus1_minus1"
                if args.mesh_frame == "alicevision_obj"
                else "none"
            ),
            "scale_applied": False,
            "sim3_applied": False,
            "icp_applied": False,
        },
        "observation_semantics": "camera_z",
        "mesh_path": str(args.mesh.resolve()),
        "mesh_sha256": route_monitor_status["attested_mesh"]["sha256"],
        "mesh_size_bytes": route_monitor_status["attested_mesh"]["size_bytes"],
        "route_provenance_path": str(args.route_provenance.resolve()),
        "route_provenance_sha256": _sha256_file(args.route_provenance),
        "route_monitor_status": route_monitor_status,
        "metrics": aggregate["metrics"],
        "frame_counts": aggregate["frame_counts"],
        "topology": topology,
        "evaluation_face_filter": evaluation_face_filter,
        "limitations": ["observation_consistency_not_ground_truth"],
    }


def _compare(args: argparse.Namespace) -> dict[str, Any]:
    tsdf = _load_json(args.tsdf)
    fusecut = _load_json(args.fusecut)
    arrays = _load_contract_archive(args.frames)
    binding, gate_contract, improvement_contract = _validate_experiment_binding(
        arrays=arrays,
        frames_path=args.frames,
        prepared_provenance_path=args.prepared_provenance,
        preregistered_contract_path=args.preregistered_contract,
        input_contract_path=args.input_contract,
        split_id=args.split_id,
        route_provenance_path=None,
    )
    if (
        tsdf.get("experiment_binding") != binding
        or fusecut.get("experiment_binding") != binding
        or tsdf.get("dataset_id") != binding["dataset_id"]
        or fusecut.get("dataset_id") != binding["dataset_id"]
        or tsdf.get("split_id") != args.split_id
        or fusecut.get("split_id") != args.split_id
    ):
        raise E.EvaluationContractError(
            E.ROUTE_INPUT_NOT_EQUIVALENT,
            "route results are not bound to the selected dataset/provenance contract",
        )
    monitor_identities = {
        "tsdf": dict(
            _revalidate_result_monitor_identity(
                tsdf,
                binding=binding,
                preregistered_contract_path=args.preregistered_contract,
                expected_phase="tsdf_meshing",
                label="TSDF",
            )
        ),
        "fusecut": dict(
            _revalidate_result_monitor_identity(
                fusecut,
                binding=binding,
                preregistered_contract_path=args.preregistered_contract,
                expected_phase="fusecut_meshing",
                label="FuseCut",
            )
        ),
    }
    comparison = E.compare_route_evaluations(
        tsdf,
        fusecut,
        expected_digest=binding["route_semantic_manifest_sha256"],
        expected_evaluation_digest=binding["evaluation_digest"],
        dataset_id=binding["dataset_id"],
        split_id=args.split_id,
        coordinate_frame=binding["coordinate_frame"],
        metres_per_model_unit=binding["metres_per_model_unit"],
        input_contract_sha256=binding["input_contract_sha256"],
        gate_contract=gate_contract,
        improvement_contract=improvement_contract,
        bootstrap_replicates=args.bootstrap_replicates,
        bootstrap_seed=args.bootstrap_seed,
    )
    comparison["route_monitor_statuses"] = monitor_identities
    return comparison


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "evaluate-fixture":
            payload = _fixture_evaluation(args)
        elif args.command == "evaluate-mesh":
            payload = _mesh_evaluation(args)
        else:
            payload = _compare(args)
        _write_new_json(args.out, payload)
        print(args.out)
        return 0
    except E.EvaluationContractError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (FileExistsError, ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
