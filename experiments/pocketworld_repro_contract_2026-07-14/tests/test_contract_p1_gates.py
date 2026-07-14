from __future__ import annotations

import hashlib
import json
import math
import subprocess
from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from pocketworld_contract import cli
from pocketworld_contract.contract import validate_contract
from pocketworld_contract.manifest import ContractError, canonical_json

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _evidence(
    evidence_id: str,
    role: str,
    *,
    path: str,
    identity_status: str = "preserved",
    commercial_gate_included: bool = False,
) -> dict[str, object]:
    item: dict[str, object] = {
        "evidence_id": evidence_id,
        "identity_status": identity_status,
        "path": path,
        "bytes": 7,
        "sha256": "a" * 64,
        "dvc_oid": "md5:0123456789abcdef0123456789abcdef",
        "producer": "fixture producer",
        "consumer": "fixture consumer",
        "inclusion_reason": "fixture evidence",
        "license_status": "verified_commercial_open_source",
        "platform_qualification": "fixture-platform",
        "evidence_role": role,
        "lineage_contains_noncommercial": False,
        "noncommercial_lineage_sources": [],
        "commercial_gate_included": commercial_gate_included,
        "replay_identity_included": False,
        "details": {},
    }
    if commercial_gate_included:
        item["license_evidence_sha256"] = "b" * 64
    else:
        item["commercial_gate_exclusion_reason"] = "Not used for a commercial verdict."
    return item


def _generic_verdict_contract() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract_id": "generic-verdict-v1",
        "contract_kind": "general_research",
        "validation_scope": "decision_contract",
        "replay_qualification": {"applicable": False},
        "status": "verdict_eligible",
        "git": {
            "repository": ".",
            "branch": "fixture",
            "commit": "a" * 40,
            "dirty_diff_sha256": "b" * 64,
        },
        "upstream": {
            "producer_stack": {
                "identity": "fixture producer",
                "revision": "fixture-v1",
                "colmap_version": "4.0.4",
                "ceres_version": "2.2",
            },
            "consumer_target_stack": {
                "identity": "PocketWorld target",
                "revision": "COLMAP-4.1.0+Ceres-2.2-submodule",
                "colmap_version": "4.1.0",
                "ceres_version": "2.2-submodule",
            },
        },
        "collections": [_evidence("fixture-input", "verdict_input", path="inputs/input.bin")],
        "code": {
            "entries": [
                {
                    "code_id": "verdict-code",
                    "path": "scripts/run.py",
                    "sha256": "c" * 64,
                    "execution_status": "runnable",
                    "role": "verdict implementation",
                    "dependency_ids": [],
                }
            ]
        },
        "environment": {
            "producer": {
                "python_version": "3.11",
                "uv_lock_sha256": "d" * 64,
                "hardware": "fixture hardware",
                "backend": "cpu",
            },
            "verifier": {
                "python_version": "3.11",
                "numpy_version": "2.4.2",
                "uv_lock_path": "uv.lock",
                "uv_lock_sha256": "e" * 64,
                "hardware": "fixture hardware",
                "backend": "cpu",
            },
        },
        "models": [],
        "effective_config": {
            "config_id": "verdict-config",
            "status": "runnable",
            "path": "configs/run.json",
            "sha256": "f" * 64,
            "values": {"grid_m": 0.01},
        },
        "seeds": {"random_seed": 0, "deterministic": True, "notes": "fixed seed"},
        "command": {
            "status": "known",
            "argv": ["python", "scripts/run.py"],
            "cwd": ".",
            "code_ids": ["verdict-code"],
            "config_id": "verdict-config",
            "dependency_ids": [],
            "model_ids": [],
        },
        "metrics": {
            "definitions": [
                {"metric_id": "quality", "unit": "ratio", "direction": "higher_is_better"}
            ],
            "thresholds": [
                {
                    "metric_id": "quality",
                    "artifact_id": "fixture-output",
                    "operator": ">=",
                    "value": 0.9,
                }
            ],
            "observed": [{"metric_id": "quality", "value": 0.95, "artifact_id": "fixture-output"}],
        },
        "exclusions": [
            {"exclusion_id": "fixture-exclusion", "rule": "exclude none", "rationale": "test"}
        ],
        "stopping_rules": [
            {"rule_id": "fixture-stop", "condition": "quality fails", "action": "fail verdict"}
        ],
        "artifacts": [_evidence("fixture-output", "verdict_output", path="outputs/output.bin")],
        "deviations": [],
        "privacy": {
            "classification": "fixture",
            "storage": "local",
            "remote_allowed": False,
            "same_disk_only": True,
            "constraints": [],
        },
        "product_qualification": {
            "status": "not_assessed",
            "commercial_open_source_dependencies_verified": False,
            "execution_dependency_closure_declared_complete": False,
            "dependencies": [],
            "reasons": ["fixture research verdict only"],
        },
        "verdict": {"eligible": True, "decision": "pass", "blockers": []},
    }


def _replay_verdict_contract() -> dict[str, object]:
    document = _generic_verdict_contract()
    document["contract_id"] = "cap51-replay-provisional-v1"
    document["contract_kind"] = "replay_fixture"
    document["replay_qualification"] = {
        "applicable": True,
        "fixture_contract_id": "cap51-replay-provisional-v1",
        "fresh_authorized_pull": False,
        "fresh_device_pull": False,
        "pull_timestamp": "2026-07-14T00:00:00Z",
        "source_device_id": "fixture-device",
        "source_app_id": "com.kyle.PocketWorld",
        "source_app_revision": "fixture-app-revision",
        "source_app_revision_proven": False,
        "source_capture_directory": "cap_1783933521157217",
        "ledger_capture_directory": "cap_1783933521157217",
        "source_quiescence_proven": False,
        "consistent_backup_proven": False,
        "atomic_db_wal_snapshot_proven": False,
        "capture_binding_proven": False,
        "integrity_check_passed": False,
        "db_pose_alignment_passed": False,
        "algorithm_revision": "0a8b8428fba3fbf942af01ada6d1e1252a677c6a",
        "incremental_global_ba_default_enabled": False,
        "control_variable": "AETHER_INCREMENTAL_GLOBAL_BA",
        "control_off_value": "unset",
        "control_on_value": "1",
        "only_control_variable_difference_proven": False,
        "db_evidence_id": "replay-db",
        "wal_evidence_id": "replay-wal",
        "pose_evidence_id": "replay-pose",
        "shm_evidence_id": "replay-shm",
    }
    document["collections"] = [
        _evidence("replay-db", "verdict_input", path="inputs/sfm_live.db"),
        _evidence("replay-wal", "verdict_input", path="inputs/sfm_live.db-wal"),
        _evidence("replay-pose", "verdict_input", path="inputs/poses.jsonl"),
    ]
    for item in document["collections"]:
        item["replay_identity_included"] = True
    report = _evidence("replay-report", "verdict_output", path="outputs/replay-report.json")
    report["details"] = {
        "fresh_authorized_pull": False,
        "source_quiescence_proven": False,
        "consistent_backup_proven": False,
        "atomic_db_wal_snapshot_proven": False,
        "capture_binding_proven": False,
        "source_app_revision_proven": False,
        "integrity_check_passed": False,
        "db_pose_alignment_passed": False,
        "ledger_capture_directory": "cap_1783933521157217",
    }
    shm = _evidence(
        "replay-shm",
        "diagnostic",
        path="inputs/sfm_live.db-shm",
        identity_status="excluded_volatile",
    )
    shm["replay_identity_included"] = True
    document["artifacts"] = [report, shm]
    document["metrics"]["observed"][0]["artifact_id"] = "replay-report"
    document["metrics"]["thresholds"][0]["artifact_id"] = "replay-report"
    return document


def _bind_typed_replay_components(document: dict[str, object]) -> None:
    component_kinds = {
        "replay-db": "sqlite_database",
        "replay-wal": "sqlite_wal",
        "replay-pose": "pose_jsonl",
        "replay-shm": "sqlite_shm",
    }
    for item in [*document["collections"], *document["artifacts"]]:
        component_kind = component_kinds.get(item["evidence_id"])
        if component_kind is not None:
            item["replay_component_kind"] = component_kind


def _dependency(dependency_id: str, kind: str = "source_code") -> dict[str, object]:
    return {
        "dependency_id": dependency_id,
        "kind": kind,
        "source": "https://example.invalid/dependency",
        "revision": "v1",
        "license_identifier": "Apache-2.0",
        "license_evidence_sha256": "1" * 64,
        "license_evidence_path": f"licenses/{dependency_id}.txt",
        "license_status": "verified_commercial_open_source",
        "audit_verdict": "allow",
        "intended_use": "commercial product integration",
        "obligations": ["preserve notices"],
        "lineage_contains_noncommercial": False,
        "noncommercial_lineage_sources": [],
    }


def test_complete_generic_research_verdict_contract_validates() -> None:
    validate_contract(_generic_verdict_contract())


@pytest.mark.parametrize(
    "empty_surface",
    [
        "collections",
        "artifacts",
        "code",
        "metric_definitions",
        "metric_thresholds",
        "metric_observations",
        "stopping_rules",
    ],
)
def test_verdict_eligible_rejects_empty_required_closure(empty_surface: str) -> None:
    document = _generic_verdict_contract()
    if empty_surface == "code":
        document["code"]["entries"] = []
    elif empty_surface.startswith("metric_"):
        key = {
            "metric_definitions": "definitions",
            "metric_thresholds": "thresholds",
            "metric_observations": "observed",
        }[empty_surface]
        document["metrics"][key] = []
    else:
        document[empty_surface] = []

    with pytest.raises(ContractError, match=r"verdict|closure|nonempty|empty"):
        validate_contract(document)


def test_provisional_contract_may_keep_metric_surfaces_empty() -> None:
    document = _generic_verdict_contract()
    document["status"] = "provisional_not_verdict_eligible"
    document["validation_scope"] = "provisional_fixture"
    document["metrics"] = {"definitions": [], "thresholds": [], "observed": []}
    document["verdict"] = {
        "eligible": False,
        "decision": "blocked_pending_review",
        "blockers": ["Metrics are not available yet."],
    }

    validate_contract(document)


@pytest.mark.parametrize(
    ("surface", "value"),
    [
        ("config", "not_applicable"),
        ("command", "not_applicable"),
        ("code", "evidence_source_not_runnable"),
    ],
)
def test_verdict_eligible_requires_runnable_registered_execution(
    surface: str,
    value: str,
) -> None:
    document = _generic_verdict_contract()
    if surface == "config":
        document["effective_config"]["status"] = value
    elif surface == "command":
        document["command"]["status"] = value
    else:
        document["code"]["entries"][0]["execution_status"] = value

    with pytest.raises(ContractError, match=r"verdict|runnable|command|config|code"):
        validate_contract(document)


def test_evidence_role_is_a_closed_vocabulary() -> None:
    document = _generic_verdict_contract()
    document["artifacts"][0]["evidence_role"] = "optimistic_output"

    with pytest.raises(ContractError, match=r"evidence_role|optimistic_output"):
        validate_contract(document)


@pytest.mark.parametrize(
    "duplicate_surface",
    ["evidence", "metric", "model", "dependency", "deviation", "exclusion", "stopping"],
)
def test_contract_rejects_duplicate_ids(duplicate_surface: str) -> None:
    document = _generic_verdict_contract()
    if duplicate_surface == "evidence":
        document["artifacts"].append(deepcopy(document["collections"][0]))
    elif duplicate_surface == "metric":
        document["metrics"]["definitions"].append(deepcopy(document["metrics"]["definitions"][0]))
    elif duplicate_surface == "model":
        model = {
            "model_id": "model-v1",
            "model_dependency_id": "model-dependency-v1",
            "training_dataset_dependency_ids": ["dataset-dependency-v1"],
            "runtime_dependency_ids": [],
            "source": "https://example.invalid/model",
            "revision": "v1",
            "weights_sha256": "2" * 64,
            "license_evidence_sha256": "3" * 64,
            "license_status": "verified_commercial_open_source",
            "audit_verdict": "allow",
            "intended_use": "commercial product inference",
            "obligations": ["preserve notices"],
            "usage": "fixture",
        }
        document["models"] = [model, deepcopy(model)]
    elif duplicate_surface == "dependency":
        dependency = _dependency("dependency-v1")
        document["product_qualification"]["dependencies"] = [dependency, deepcopy(dependency)]
    elif duplicate_surface == "deviation":
        deviation = {
            "deviation_id": "deviation-v1",
            "field": "/metrics",
            "reason": "fixture",
            "blocks_verdict": False,
            "resolution": "fixture",
        }
        document["deviations"] = [deviation, deepcopy(deviation)]
    elif duplicate_surface == "exclusion":
        document["exclusions"].append(deepcopy(document["exclusions"][0]))
    else:
        document["stopping_rules"].append(deepcopy(document["stopping_rules"][0]))

    with pytest.raises(ContractError, match=r"duplicate|unique|identifier|ID"):
        validate_contract(document)


@pytest.mark.parametrize("nonfinite", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("surface", ["threshold", "observation"])
def test_contract_rejects_nonfinite_metric_numbers(surface: str, nonfinite: float) -> None:
    document = _generic_verdict_contract()
    if surface == "threshold":
        document["metrics"]["thresholds"][0]["value"] = nonfinite
    else:
        document["metrics"]["observed"][0]["value"] = nonfinite

    with pytest.raises(ContractError, match=r"finite|NaN|Infinity|metric"):
        validate_contract(document)


@pytest.mark.parametrize(
    ("operator", "passing_value", "failing_value"),
    [
        (">", 1.1, 1.0),
        (">=", 1.0, 0.9),
        ("<", 0.9, 1.0),
        ("<=", 1.0, 1.1),
        ("==", 1.0, 1.1),
    ],
)
def test_verdict_decision_matches_evaluated_numeric_thresholds(
    operator: str,
    passing_value: float,
    failing_value: float,
) -> None:
    passing = _generic_verdict_contract()
    passing["metrics"]["thresholds"][0].update({"operator": operator, "value": 1.0})
    passing["metrics"]["observed"][0]["value"] = passing_value
    validate_contract(passing)

    wrong_pass = deepcopy(passing)
    wrong_pass["verdict"]["decision"] = "fail"
    with pytest.raises(ContractError, match=r"decision|threshold|result"):
        validate_contract(wrong_pass)

    failing = deepcopy(passing)
    failing["metrics"]["observed"][0]["value"] = failing_value
    failing["verdict"]["decision"] = "fail"
    validate_contract(failing)

    wrong_fail = deepcopy(failing)
    wrong_fail["verdict"]["decision"] = "pass"
    with pytest.raises(ContractError, match=r"decision|threshold|result"):
        validate_contract(wrong_fail)


def test_arbitrarily_large_json_integers_remain_finite_metric_numbers() -> None:
    document = _generic_verdict_contract()
    large_integer = 10**400
    document["metrics"]["thresholds"][0].update({"operator": "==", "value": large_integer})
    document["metrics"]["observed"][0]["value"] = large_integer

    validate_contract(document)


@pytest.mark.parametrize("nonnumeric", ["0.95", True, False])
def test_decision_threshold_rejects_string_or_boolean_observation(nonnumeric: object) -> None:
    document = _generic_verdict_contract()
    document["metrics"]["observed"][0]["value"] = nonnumeric

    with pytest.raises(ContractError, match=r"numeric|number|threshold|observation"):
        validate_contract(document)


def test_verdict_threshold_requires_an_explicit_output_artifact() -> None:
    document = _generic_verdict_contract()
    del document["metrics"]["thresholds"][0]["artifact_id"]

    with pytest.raises(ContractError, match=r"artifact|threshold|closure"):
        validate_contract(document)


def test_one_verdict_report_can_back_multiple_distinct_metrics() -> None:
    document = _generic_verdict_contract()
    document["metrics"]["definitions"].append(
        {"metric_id": "coverage", "unit": "ratio", "direction": "higher_is_better"}
    )
    document["metrics"]["thresholds"].append(
        {
            "metric_id": "coverage",
            "artifact_id": "fixture-output",
            "operator": ">=",
            "value": 0.8,
        }
    )
    document["metrics"]["observed"].append(
        {"metric_id": "coverage", "value": 0.9, "artifact_id": "fixture-output"}
    )

    validate_contract(document)


def test_verdict_rejects_duplicate_threshold_metric_artifact_pairs() -> None:
    document = _generic_verdict_contract()
    document["metrics"]["thresholds"].append(deepcopy(document["metrics"]["thresholds"][0]))

    with pytest.raises(ContractError, match=r"duplicate|threshold|metric/artifact|unique"):
        validate_contract(document)


@pytest.mark.parametrize("broken_ref", ["threshold_metric", "observation_metric", "artifact"])
def test_metric_and_artifact_references_are_closed(broken_ref: str) -> None:
    document = _generic_verdict_contract()
    if broken_ref == "threshold_metric":
        document["metrics"]["thresholds"][0]["metric_id"] = "undefined"
    elif broken_ref == "observation_metric":
        document["metrics"]["observed"][0]["metric_id"] = "undefined"
    else:
        document["metrics"]["observed"][0]["artifact_id"] = "undefined"

    with pytest.raises(ContractError, match=r"metric|artifact|reference|undefined"):
        validate_contract(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("path", "../outside.bin"),
        ("path", ""),
        ("dvc_oid", "pretend-dvc-object"),
        ("producer", ""),
        ("consumer", ""),
        ("platform_qualification", ""),
    ],
)
def test_verdict_evidence_requires_complete_safe_identity(field: str, value: str) -> None:
    document = _generic_verdict_contract()
    document["collections"][0][field] = value

    with pytest.raises(
        ContractError,
        match=r"evidence|path|[Dd][Vv][Cc]|producer|consumer|platform",
    ):
        validate_contract(document)


def test_decision_observation_requires_a_preserved_verdict_output() -> None:
    document = _generic_verdict_contract()
    document["artifacts"][0]["identity_status"] = "source_evidence_only"
    document["artifacts"][0]["evidence_role"] = "diagnostic"

    with pytest.raises(ContractError, match=r"observation|preserved|verdict_output"):
        validate_contract(document)


@pytest.mark.parametrize(
    "dvc_oid",
    ["md5:" + "0" * 32, "md5:0123456789abcdef0123456789abcdef.dir"],
)
def test_verdict_evidence_rejects_fake_or_directory_dvc_identity(dvc_oid: str) -> None:
    document = _generic_verdict_contract()
    document["collections"][0]["dvc_oid"] = dvc_oid

    with pytest.raises(ContractError, match=r"DVC|dvc|single-file"):
        validate_contract(document)


def test_commercial_candidate_requires_included_verdict_evidence() -> None:
    document = _generic_verdict_contract()
    document["product_qualification"] = {
        "status": "commercial_evaluation_candidate",
        "commercial_open_source_dependencies_verified": True,
        "execution_dependency_closure_declared_complete": False,
        "dependencies": [_dependency("source-v1")],
        "reasons": [],
    }

    with pytest.raises(ContractError, match=r"commercial|included|verdict"):
        validate_contract(document)


def _commercial_candidate() -> dict[str, object]:
    document = _generic_verdict_contract()
    for item in [*document["collections"], *document["artifacts"]]:
        item["commercial_gate_included"] = True
        item["license_evidence_sha256"] = "9" * 64
        item.pop("commercial_gate_exclusion_reason")
    document["product_qualification"] = {
        "status": "commercial_evaluation_candidate",
        "commercial_open_source_dependencies_verified": True,
        "execution_dependency_closure_declared_complete": True,
        "dependencies": [_dependency("source-v1")],
        "reasons": [],
    }
    document["code"]["entries"][0]["dependency_ids"] = ["source-v1"]
    document["command"]["dependency_ids"] = ["source-v1"]
    return document


def test_commercial_candidate_rejects_excluded_noncommercial_verdict_input() -> None:
    document = _commercial_candidate()
    excluded_input = _evidence(
        "excluded-noncommercial-input",
        "verdict_input",
        path="inputs/excluded-noncommercial.bin",
    )
    excluded_input.update(
        {
            "license_status": "noncommercial_ineligible",
            "lineage_contains_noncommercial": True,
            "noncommercial_lineage_sources": ["excluded benchmark fixture"],
        }
    )
    document["collections"].append(excluded_input)

    with pytest.raises(ContractError, match=r"commercial|verdict_input|included|lineage"):
        validate_contract(document)


def _commercial_model_candidate() -> dict[str, object]:
    document = _commercial_candidate()
    model_dependency = _dependency("model-v1", "model")
    model_dependency.update(
        {
            "source": "https://example.invalid/model",
            "revision": "model-revision-v1",
            "license_evidence_sha256": "3" * 64,
            "license_evidence_path": "licenses/model-v1.txt",
            "intended_use": "commercial product inference",
        }
    )
    dataset_dependency = _dependency("dataset-v1", "dataset")
    document["product_qualification"]["dependencies"].extend([model_dependency, dataset_dependency])
    document["models"] = [
        {
            "model_id": "fixture-model",
            "model_dependency_id": "model-v1",
            "training_dataset_dependency_ids": ["dataset-v1"],
            "runtime_dependency_ids": ["source-v1"],
            "source": "https://example.invalid/model",
            "revision": "model-revision-v1",
            "weights_path": "models/fixture-model.bin",
            "weights_sha256": "2" * 64,
            "license_evidence_path": "licenses/model-v1.txt",
            "license_evidence_sha256": "3" * 64,
            "license_status": "verified_commercial_open_source",
            "audit_verdict": "allow",
            "intended_use": "commercial product inference",
            "obligations": ["preserve notices"],
            "usage": "fixture inference",
        }
    ]
    document["command"]["model_ids"] = ["fixture-model"]
    return document


def test_commercial_candidate_accepts_documented_user_owned_input_and_output() -> None:
    document = _commercial_candidate()
    for item, license_status in (
        (document["collections"][0], "user_owned_private_input"),
        (document["artifacts"][0], "user_owned_derived_output"),
    ):
        item["license_status"] = license_status
        item.pop("license_evidence_sha256")
        item["rights_basis"] = "The user owns the captured and derived evidence."
        item["rights_evidence_sha256"] = "8" * 64

    validate_contract(document)


def test_commercial_candidate_accepts_explicit_model_legal_and_weight_identity() -> None:
    validate_contract(_commercial_model_candidate())


@pytest.mark.parametrize(
    ("surface", "path"),
    [
        ("weights_path", ("models", 0, "weights_path")),
        ("model_license_path", ("models", 0, "license_evidence_path")),
        (
            "dependency_license_path",
            ("product_qualification", "dependencies", 1, "license_evidence_path"),
        ),
    ],
)
def test_commercial_model_candidate_requires_rehashable_local_evidence_paths(
    surface: str,
    path: tuple[object, ...],
) -> None:
    assert surface
    document = _commercial_model_candidate()
    target: object = document
    for component in path[:-1]:
        target = target[component]
    del target[path[-1]]

    with pytest.raises(ContractError, match=r"model|weight|license|evidence|commercial"):
        validate_contract(document)


def test_commercial_candidate_rejects_conditional_dependency_audit() -> None:
    document = _commercial_candidate()
    document["product_qualification"]["dependencies"][0]["audit_verdict"] = "conditional"

    with pytest.raises(ContractError, match=r"commercial|audit|dependenc"):
        validate_contract(document)


def test_used_model_requires_explicit_model_and_dataset_dependency_references() -> None:
    document = _generic_verdict_contract()
    document["models"] = [
        {
            "model_id": "model-v1",
            "model_dependency_id": "missing-model-dependency",
            "training_dataset_dependency_ids": ["missing-dataset-dependency"],
            "runtime_dependency_ids": [],
            "source": "https://example.invalid/model",
            "revision": "v1",
            "weights_sha256": "2" * 64,
            "license_evidence_sha256": "3" * 64,
            "license_status": "verified_commercial_open_source",
            "audit_verdict": "allow",
            "intended_use": "commercial product inference",
            "obligations": ["preserve notices"],
            "usage": "fixture",
        }
    ]
    document["product_qualification"]["dependencies"] = [_dependency("unrelated-source")]

    with pytest.raises(ContractError, match=r"model|dataset|dependency|reference"):
        validate_contract(document)


@pytest.mark.parametrize(
    ("surface", "mutation"),
    [
        ("code", lambda document: document["code"]["entries"][0].update(dependency_ids=[])),
        ("command", lambda document: document["command"].update(dependency_ids=[])),
        (
            "closure declaration",
            lambda document: document["product_qualification"].update(
                execution_dependency_closure_declared_complete=False
            ),
        ),
    ],
)
def test_commercial_candidate_rejects_an_empty_execution_dependency_surface(
    surface: str,
    mutation: Callable[[dict[str, object]], None],
) -> None:
    assert surface
    document = _commercial_candidate()
    mutation(document)

    with pytest.raises(ContractError, match=r"commercial|dependency|closure|execution"):
        validate_contract(document)


def test_commercial_candidate_rejects_unreferenced_dependency_padding() -> None:
    document = _commercial_candidate()
    document["product_qualification"]["dependencies"].append(_dependency("unused-tool", "tool"))

    with pytest.raises(ContractError, match=r"dependency|unreferenced|closure"):
        validate_contract(document)


@pytest.mark.parametrize("laundered_kind", ["model", "dataset"])
def test_commercial_candidate_rejects_typed_dependency_laundered_through_execution_slots(
    laundered_kind: str,
) -> None:
    document = _commercial_candidate()
    dependency_id = f"laundered-{laundered_kind}"
    document["product_qualification"]["dependencies"].append(
        _dependency(dependency_id, laundered_kind)
    )
    document["code"]["entries"][0]["dependency_ids"].append(dependency_id)
    document["command"]["dependency_ids"].append(dependency_id)

    with pytest.raises(ContractError, match=r"dependency|kind|model|dataset|slot|closure"):
        validate_contract(document)


def test_commercial_model_dependency_is_backed_by_exactly_one_model_record() -> None:
    document = _commercial_model_candidate()
    duplicate = deepcopy(document["models"][0])
    duplicate["model_id"] = "duplicate-fixture-model"
    document["models"].append(duplicate)
    document["command"]["model_ids"].append("duplicate-fixture-model")

    with pytest.raises(ContractError, match=r"model|dependency|exactly one|duplicate"):
        validate_contract(document)


@pytest.mark.parametrize("surface", ["code_ids", "config_id"])
def test_known_verdict_command_must_reference_runnable_code_and_config(surface: str) -> None:
    document = _generic_verdict_contract()
    if surface == "code_ids":
        document["command"][surface] = ["missing-code"]
    else:
        document["command"][surface] = "missing-config"

    with pytest.raises(ContractError, match=r"command|code|config|reference"):
        validate_contract(document)


def test_known_verdict_command_cannot_omit_a_runnable_code_entry() -> None:
    document = _generic_verdict_contract()
    document["code"]["entries"].append(
        {
            "code_id": "second-code",
            "path": "scripts/second.py",
            "sha256": "1" * 64,
            "execution_status": "runnable",
            "role": "second execution unit",
            "dependency_ids": [],
        }
    )

    with pytest.raises(ContractError, match=r"command|code|reference|runnable"):
        validate_contract(document)


def test_known_verdict_command_cannot_omit_a_declared_used_model() -> None:
    document = _commercial_model_candidate()
    document["product_qualification"].update(
        {
            "status": "not_assessed",
            "commercial_open_source_dependencies_verified": False,
            "execution_dependency_closure_declared_complete": False,
            "reasons": ["commercial qualification intentionally disabled for this test"],
        }
    )
    document["command"]["model_ids"] = []

    with pytest.raises(ContractError, match=r"command|model|reference|used"):
        validate_contract(document)


def test_replay_contract_cannot_upgrade_from_untyped_details() -> None:
    document = _replay_verdict_contract()

    with pytest.raises(ContractError, match=r"replay|fresh|quies|binding|atomic|integrity"):
        validate_contract(document)


def test_replay_contract_excludes_shm_from_identity() -> None:
    document = _replay_verdict_contract()
    document["artifacts"][0]["details"] = {}
    document["artifacts"][1]["replay_identity_included"] = True

    with pytest.raises(ContractError, match=r"SHM|shm|excluded|identity"):
        validate_contract(document)


def test_replay_component_references_are_pairwise_distinct_while_provisional() -> None:
    document = _replay_verdict_contract()
    document["status"] = "provisional_not_verdict_eligible"
    document["validation_scope"] = "provisional_fixture"
    document["verdict"] = {
        "eligible": False,
        "decision": "blocked_pending_review",
        "blockers": ["Replay evidence remains provisional."],
    }
    document["replay_qualification"]["wal_evidence_id"] = document["replay_qualification"][
        "db_evidence_id"
    ]
    document["artifacts"][0]["details"] = {}
    document["artifacts"][1]["replay_identity_included"] = False

    with pytest.raises(ContractError, match=r"replay|distinct|alias|component"):
        validate_contract(document)


@pytest.mark.parametrize(
    ("evidence_id", "invalid_kind"),
    [
        ("replay-db", None),
        ("replay-wal", "sqlite_database"),
        ("replay-pose", "sqlite_wal"),
        ("replay-shm", "pose_jsonl"),
    ],
)
def test_provisional_replay_refs_require_correct_typed_component_binding(
    evidence_id: str,
    invalid_kind: str | None,
) -> None:
    document = _replay_verdict_contract()
    document["status"] = "provisional_not_verdict_eligible"
    document["validation_scope"] = "provisional_fixture"
    document["verdict"] = {
        "eligible": False,
        "decision": "blocked_pending_review",
        "blockers": ["Replay evidence remains provisional."],
    }
    document["artifacts"][0]["details"] = {}
    document["artifacts"][1]["replay_identity_included"] = False
    _bind_typed_replay_components(document)
    evidence = {
        item["evidence_id"]: item for item in [*document["collections"], *document["artifacts"]]
    }
    if invalid_kind is None:
        evidence[evidence_id].pop("replay_component_kind")
    else:
        evidence[evidence_id]["replay_component_kind"] = invalid_kind

    with pytest.raises(ContractError, match=r"replay|component|kind|binding"):
        validate_contract(document)


def test_complete_typed_replay_contract_validates() -> None:
    document = _replay_verdict_contract()
    document["contract_id"] = "cap51-replay-fixture-v2"
    qualification = document["replay_qualification"]
    qualification["fixture_contract_id"] = document["contract_id"]
    for key in (
        "fresh_authorized_pull",
        "fresh_device_pull",
        "source_app_revision_proven",
        "source_quiescence_proven",
        "atomic_db_wal_snapshot_proven",
        "capture_binding_proven",
        "integrity_check_passed",
        "db_pose_alignment_passed",
        "only_control_variable_difference_proven",
    ):
        qualification[key] = True
    document["artifacts"][0]["details"] = {}
    document["artifacts"][1]["replay_identity_included"] = False
    _bind_typed_replay_components(document)

    validate_contract(document)


@pytest.mark.parametrize(
    ("evidence_id", "wrong_kind"),
    [
        ("replay-db", "sqlite_wal"),
        ("replay-wal", "pose_jsonl"),
        ("replay-pose", "sqlite_database"),
        ("replay-shm", "sqlite_database"),
    ],
)
def test_replay_verdict_rejects_wrong_typed_component_binding(
    evidence_id: str,
    wrong_kind: str,
) -> None:
    document = _replay_verdict_contract()
    document["contract_id"] = "cap51-replay-fixture-v2"
    qualification = document["replay_qualification"]
    qualification["fixture_contract_id"] = document["contract_id"]
    for key in (
        "fresh_authorized_pull",
        "fresh_device_pull",
        "source_app_revision_proven",
        "source_quiescence_proven",
        "atomic_db_wal_snapshot_proven",
        "capture_binding_proven",
        "integrity_check_passed",
        "db_pose_alignment_passed",
        "only_control_variable_difference_proven",
    ):
        qualification[key] = True
    document["artifacts"][0]["details"] = {}
    document["artifacts"][1]["replay_identity_included"] = False
    _bind_typed_replay_components(document)
    evidence = {
        item["evidence_id"]: item for item in [*document["collections"], *document["artifacts"]]
    }
    evidence[evidence_id]["replay_component_kind"] = wrong_kind

    with pytest.raises(ContractError, match=r"replay|component|kind|binding"):
        validate_contract(document)


@pytest.mark.parametrize(
    "field",
    [
        "fresh_authorized_pull",
        "fresh_device_pull",
        "source_app_revision_proven",
        "source_quiescence_proven",
        "atomic_db_wal_snapshot_proven",
        "capture_binding_proven",
        "integrity_check_passed",
        "db_pose_alignment_passed",
        "only_control_variable_difference_proven",
    ],
)
def test_replay_verdict_rejects_each_unproven_typed_gate(field: str) -> None:
    document = _replay_verdict_contract()
    document["contract_id"] = "cap51-replay-fixture-v2"
    qualification = document["replay_qualification"]
    qualification["fixture_contract_id"] = document["contract_id"]
    for key in (
        "fresh_authorized_pull",
        "fresh_device_pull",
        "source_app_revision_proven",
        "source_quiescence_proven",
        "atomic_db_wal_snapshot_proven",
        "capture_binding_proven",
        "integrity_check_passed",
        "db_pose_alignment_passed",
        "only_control_variable_difference_proven",
    ):
        qualification[key] = True
    qualification[field] = False
    document["artifacts"][0]["details"] = {}
    document["artifacts"][1]["replay_identity_included"] = False

    with pytest.raises(ContractError, match=r"replay|device|revision|control|integrity|binding"):
        validate_contract(document)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("algorithm_revision", "8952bfc000000000000000000000000000000000"),
        ("incremental_global_ba_default_enabled", True),
        ("control_variable", "AETHER_MIRROR_CULL"),
        ("control_off_value", "0"),
        ("control_on_value", "true"),
    ],
)
def test_replay_verdict_pins_clean_incremental_ba_control_identity(
    field: str,
    invalid: object,
) -> None:
    document = _replay_verdict_contract()
    document["contract_id"] = "cap51-replay-fixture-v2"
    qualification = document["replay_qualification"]
    qualification["fixture_contract_id"] = document["contract_id"]
    for key in (
        "fresh_authorized_pull",
        "fresh_device_pull",
        "source_app_revision_proven",
        "source_quiescence_proven",
        "atomic_db_wal_snapshot_proven",
        "capture_binding_proven",
        "integrity_check_passed",
        "db_pose_alignment_passed",
        "only_control_variable_difference_proven",
    ):
        qualification[key] = True
    qualification[field] = invalid
    document["artifacts"][0]["details"] = {}
    document["artifacts"][1]["replay_identity_included"] = False

    with pytest.raises(ContractError, match=r"replay|revision|incremental|control|default"):
        validate_contract(document)


@pytest.mark.parametrize(
    ("command", "raw"),
    [
        ("verify-contract", b'{"schema_version":1,"schema_version":1}\n'),
        ("gate-verdict", b'{"status":"verdict_eligible","status":"verdict_eligible"}\n'),
        ("verify-contract", b'{"schema_version":NaN}\n'),
        ("verify-contract", b'{"schema_version":Infinity}\n'),
        ("verify-contract", b'{"schema_version":1e9999}\n'),
        ("verify-contract", b'{"schema_version":-1e9999}\n'),
        ("verify-contract", b'{\n  "schema_version": 1\n}\n'),
        ("verify-contract", b'{"schema_version":1}'),
    ],
)
def test_cli_contract_commands_reject_non_strict_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    raw: bytes,
) -> None:
    path = tmp_path / "contract.json"
    path.write_bytes(raw)
    monkeypatch.setattr(cli, "validate_contract", lambda _document: None)
    monkeypatch.setattr(cli, "require_verdict_eligible", lambda _document: None)

    assert cli.main([command, str(path)]) == 2


@pytest.mark.parametrize("overflow", ["1e9999", "-1e9999"])
def test_cli_rejects_overflowing_json_float_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    overflow: str,
) -> None:
    path = tmp_path / "contract.json"
    path.write_text(f'{{"schema_version":{overflow}}}\n', encoding="utf-8")
    monkeypatch.setattr(cli, "validate_contract", lambda _document: None)

    assert cli.main(["verify-contract", str(path)]) == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "finite" in captured.err


def _run_git(root: Path, *args: str) -> str:
    completed = subprocess.run(  # noqa: S603 - fixed executable, argv list, no shell.
        ["/usr/bin/git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _write_verdict_repo(
    tmp_path: Path,
    *,
    provisional: bool = False,
) -> tuple[Path, dict[str, Path]]:
    root = tmp_path / "repo"
    root.mkdir()
    _run_git(root, "init", "-b", "fixture")
    _run_git(root, "config", "user.name", "Contract Test")
    _run_git(root, "config", "user.email", "contract-test@example.invalid")
    files = {
        "input": root / "inputs/input.bin",
        "output": root / "outputs/output.bin",
        "code": root / "scripts/run.py",
        "config": root / "configs/run.json",
        "lock": root / "uv.lock",
    }
    for name, path in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{name}-fixture".encode())
    _run_git(root, "add", "inputs", "outputs", "scripts", "configs", "uv.lock")
    _run_git(root, "commit", "-m", "fixture inputs")
    execution_commit = _run_git(root, "rev-parse", "HEAD")

    document = _generic_verdict_contract()
    document["git"] = {
        "repository": ".",
        "branch": "fixture",
        "commit": execution_commit,
        "dirty_diff_sha256": hashlib.sha256(b"").hexdigest(),
    }
    if provisional:
        document["status"] = "provisional_not_verdict_eligible"
        document["validation_scope"] = "provisional_fixture"
        document["verdict"] = {
            "eligible": False,
            "decision": "blocked_pending_review",
            "blockers": ["fixture remains provisional"],
        }
    for item, key in (
        (document["collections"][0], "input"),
        (document["artifacts"][0], "output"),
    ):
        payload = files[key].read_bytes()
        item["bytes"] = len(payload)
        item["sha256"] = hashlib.sha256(payload).hexdigest()
        item["dvc_oid"] = f"md5:{hashlib.md5(payload, usedforsecurity=False).hexdigest()}"
    for entry in document["code"]["entries"]:
        entry["sha256"] = hashlib.sha256(files["code"].read_bytes()).hexdigest()
    document["effective_config"]["sha256"] = hashlib.sha256(
        files["config"].read_bytes()
    ).hexdigest()
    document["environment"]["verifier"]["uv_lock_sha256"] = hashlib.sha256(
        files["lock"].read_bytes()
    ).hexdigest()
    contract_path = root / "contracts/verdict.json"
    contract_path.parent.mkdir()
    contract_path.write_text(canonical_json(document), encoding="utf-8")
    _run_git(root, "add", "contracts/verdict.json")
    _run_git(root, "commit", "-m", "record contract")
    return contract_path, files


def _write_claimed_execution_repository(root: Path, source_files: dict[str, Path]) -> str:
    root.mkdir()
    _run_git(root, "init", "-b", "fixture")
    _run_git(root, "config", "user.name", "Contract Test")
    _run_git(root, "config", "user.email", "contract-test@example.invalid")
    destinations = {
        "input": "inputs/input.bin",
        "output": "outputs/output.bin",
        "code": "scripts/run.py",
        "config": "configs/run.json",
        "lock": "uv.lock",
    }
    for key, relative_path in destinations.items():
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_files[key].read_bytes())
    _run_git(root, "add", ".")
    _run_git(root, "commit", "-m", "claimed execution evidence")
    return _run_git(root, "rev-parse", "HEAD")


def _retarget_contract_git_repository(
    contract_path: Path,
    *,
    repository: str,
    commit: str,
) -> None:
    document = json.loads(contract_path.read_text(encoding="utf-8"))
    document["git"] = {
        "repository": repository,
        "branch": "fixture",
        "commit": commit,
        "dirty_diff_sha256": hashlib.sha256(b"").hexdigest(),
    }
    contract_path.write_text(canonical_json(document), encoding="utf-8")


def test_cli_verifies_repository_and_file_identity_for_a_clean_contract(tmp_path: Path) -> None:
    contract_path, _files = _write_verdict_repo(tmp_path)

    assert cli.main(["verify-contract", str(contract_path)]) == 0


def test_cli_verifies_non_verdict_repository_claims_in_a_provisional_contract(
    tmp_path: Path,
) -> None:
    contract_path, _files = _write_verdict_repo(tmp_path, provisional=True)

    assert cli.main(["verify-contract", str(contract_path)]) == 0


def test_cli_accepts_a_lexically_nested_real_git_root(tmp_path: Path) -> None:
    contract_path, files = _write_verdict_repo(tmp_path)
    outer_root = contract_path.parents[1]
    nested_root = outer_root / "nested"
    nested_commit = _write_claimed_execution_repository(nested_root, files)
    _retarget_contract_git_repository(
        contract_path,
        repository="nested",
        commit=nested_commit,
    )

    assert cli.main(["verify-contract", str(contract_path)]) == 0


def test_cli_rejects_nested_git_root_claim_through_a_symlink_escape(tmp_path: Path) -> None:
    contract_path, files = _write_verdict_repo(tmp_path)
    outer_root = contract_path.parents[1]
    external_root = tmp_path / "external-repository"
    external_commit = _write_claimed_execution_repository(external_root, files)
    (outer_root / "nested").symlink_to(external_root, target_is_directory=True)
    _retarget_contract_git_repository(
        contract_path,
        repository="nested",
        commit=external_commit,
    )

    assert cli.main(["verify-contract", str(contract_path)]) == 2


@pytest.mark.parametrize("tampered", ["input", "output", "code", "config", "lock"])
def test_cli_rehashes_repo_local_provisional_claims(tmp_path: Path, tampered: str) -> None:
    contract_path, files = _write_verdict_repo(tmp_path, provisional=True)
    files[tampered].write_bytes(b"tampered")

    assert cli.main(["verify-contract", str(contract_path)]) == 2


def _downgrade_git_dirty_claim(document: dict[str, object]) -> None:
    document["git"]["dirty_diff_sha256"] = None
    document["deviations"].append(
        {
            "deviation_id": "fixture-dirty-diff-not-recorded",
            "field": "/git/dirty_diff_sha256",
            "reason": "This fixture intentionally isolates repository-file rehash behavior.",
            "blocks_verdict": False,
            "resolution": "Record a dirty diff before a real verdict.",
        }
    )


def _downgrade_source_dvc_claim(document: dict[str, object]) -> None:
    document["collections"][0]["dvc_oid"] = None
    document["deviations"].append(
        {
            "deviation_id": "fixture-source-dvc-not-created",
            "field": "/collections/0/dvc_oid",
            "reason": "The source evidence has not been preserved in DVC.",
            "blocks_verdict": False,
            "resolution": "Preserve the payload before a real verdict.",
        }
    )


def test_cli_rehashes_available_repo_local_source_evidence_in_provisional_contract(
    tmp_path: Path,
) -> None:
    contract_path, files = _write_verdict_repo(tmp_path, provisional=True)
    document = json.loads(contract_path.read_text(encoding="utf-8"))
    document["collections"][0]["identity_status"] = "source_evidence_only"
    _downgrade_git_dirty_claim(document)
    _downgrade_source_dvc_claim(document)
    contract_path.write_text(canonical_json(document), encoding="utf-8")
    _run_git(contract_path.parents[1], "add", "contracts/verdict.json")
    _run_git(contract_path.parents[1], "commit", "-m", "downgrade input preservation claim")

    assert cli.main(["verify-contract", str(contract_path)]) == 0
    files["input"].write_bytes(b"tampered")
    assert cli.main(["verify-contract", str(contract_path)]) == 2


def test_cli_skips_unpreserved_external_source_payload_that_is_not_materialized(
    tmp_path: Path,
) -> None:
    contract_path, _files = _write_verdict_repo(tmp_path, provisional=True)
    document = json.loads(contract_path.read_text(encoding="utf-8"))
    item = document["collections"][0]
    item["identity_status"] = "source_evidence_only"
    item["path"] = "external-private/cap51-input.bin"
    _downgrade_git_dirty_claim(document)
    _downgrade_source_dvc_claim(document)
    contract_path.write_text(canonical_json(document), encoding="utf-8")
    _run_git(contract_path.parents[1], "add", "contracts/verdict.json")
    _run_git(contract_path.parents[1], "commit", "-m", "record external source identity")

    assert cli.main(["verify-contract", str(contract_path)]) == 0


def test_cli_does_not_treat_a_symlinked_missing_source_as_absent_external_evidence(
    tmp_path: Path,
) -> None:
    contract_path, _files = _write_verdict_repo(tmp_path, provisional=True)
    document = json.loads(contract_path.read_text(encoding="utf-8"))
    item = document["collections"][0]
    item["identity_status"] = "source_evidence_only"
    item["path"] = "external-private/cap51-input.bin"
    _downgrade_git_dirty_claim(document)
    _downgrade_source_dvc_claim(document)
    contract_path.write_text(canonical_json(document), encoding="utf-8")
    root = contract_path.parents[1]
    _run_git(root, "add", "contracts/verdict.json")
    _run_git(root, "commit", "-m", "record external source identity")
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "external-private").symlink_to(outside, target_is_directory=True)

    assert cli.main(["verify-contract", str(contract_path)]) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("branch", "other-branch"),
        ("commit", "f" * 40),
        ("repository", "../outside"),
    ],
)
def test_cli_rejects_false_git_identity_claims(
    tmp_path: Path,
    field: str,
    value: str,
) -> None:
    contract_path, _files = _write_verdict_repo(tmp_path)
    document = json.loads(contract_path.read_text(encoding="utf-8"))
    document["git"][field] = value
    contract_path.write_text(canonical_json(document), encoding="utf-8")
    _run_git(contract_path.parents[1], "add", "contracts/verdict.json")
    _run_git(contract_path.parents[1], "commit", "-m", f"tamper {field} claim")

    assert cli.main(["verify-contract", str(contract_path)]) == 2


def _write_commercial_model_repo(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    contract_path, files = _write_verdict_repo(tmp_path)
    root = contract_path.parents[1]
    extra_files = {
        "source_license": root / "licenses/source-v1.txt",
        "model_license": root / "licenses/model-v1.txt",
        "dataset_license": root / "licenses/dataset-v1.txt",
        "weights": root / "models/fixture-model.bin",
    }
    for name, path in extra_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"{name}-fixture".encode())
    _run_git(root, "add", "licenses", "models")
    _run_git(root, "commit", "-m", "add model legal evidence")
    execution_commit = _run_git(root, "rev-parse", "HEAD")

    document = json.loads(contract_path.read_text(encoding="utf-8"))
    for item, license_status in (
        (document["collections"][0], "user_owned_private_input"),
        (document["artifacts"][0], "user_owned_derived_output"),
    ):
        item["license_status"] = license_status
        item["commercial_gate_included"] = True
        item.pop("commercial_gate_exclusion_reason")
        item.pop("license_evidence_sha256", None)
        item["rights_basis"] = "User-owned fixture evidence."
        item["rights_evidence_sha256"] = "8" * 64

    source_dependency = _dependency("source-v1")
    model_dependency = _dependency("model-v1", "model")
    dataset_dependency = _dependency("dataset-v1", "dataset")
    dependency_files = {
        "source-v1": extra_files["source_license"],
        "model-v1": extra_files["model_license"],
        "dataset-v1": extra_files["dataset_license"],
    }
    for dependency in (source_dependency, model_dependency, dataset_dependency):
        dependency["license_evidence_sha256"] = hashlib.sha256(
            dependency_files[dependency["dependency_id"]].read_bytes()
        ).hexdigest()
    model_dependency.update(
        {
            "source": "https://example.invalid/model",
            "revision": "model-revision-v1",
            "intended_use": "commercial product inference",
        }
    )
    document["product_qualification"] = {
        "status": "commercial_evaluation_candidate",
        "commercial_open_source_dependencies_verified": True,
        "execution_dependency_closure_declared_complete": True,
        "dependencies": [source_dependency, model_dependency, dataset_dependency],
        "reasons": [],
    }
    document["code"]["entries"][0]["dependency_ids"] = ["source-v1"]
    document["command"]["dependency_ids"] = ["source-v1"]
    document["command"]["model_ids"] = ["fixture-model"]
    document["models"] = [
        {
            "model_id": "fixture-model",
            "model_dependency_id": "model-v1",
            "training_dataset_dependency_ids": ["dataset-v1"],
            "runtime_dependency_ids": ["source-v1"],
            "source": model_dependency["source"],
            "revision": model_dependency["revision"],
            "weights_path": "models/fixture-model.bin",
            "weights_sha256": hashlib.sha256(extra_files["weights"].read_bytes()).hexdigest(),
            "license_evidence_path": model_dependency["license_evidence_path"],
            "license_evidence_sha256": model_dependency["license_evidence_sha256"],
            "license_status": model_dependency["license_status"],
            "audit_verdict": model_dependency["audit_verdict"],
            "intended_use": model_dependency["intended_use"],
            "obligations": model_dependency["obligations"],
            "usage": "fixture inference",
        }
    ]
    document["git"]["commit"] = execution_commit
    document["git"]["dirty_diff_sha256"] = hashlib.sha256(b"").hexdigest()
    contract_path.write_text(canonical_json(document), encoding="utf-8")
    _run_git(root, "add", "contracts/verdict.json")
    _run_git(root, "commit", "-m", "record commercial model contract")
    files.update(extra_files)
    return contract_path, files


def test_cli_rehashes_model_weights_and_license_evidence(tmp_path: Path) -> None:
    contract_path, files = _write_commercial_model_repo(tmp_path)
    assert cli.main(["verify-contract", str(contract_path)]) == 0

    files["weights"].write_bytes(b"tampered")
    assert cli.main(["verify-contract", str(contract_path)]) == 2


def test_cli_rehashes_product_dependency_license_evidence(tmp_path: Path) -> None:
    contract_path, files = _write_commercial_model_repo(tmp_path)
    assert cli.main(["verify-contract", str(contract_path)]) == 0

    files["dataset_license"].write_bytes(b"tampered")
    assert cli.main(["verify-contract", str(contract_path)]) == 2


@pytest.mark.parametrize("tampered", ["input", "output", "code", "config", "lock"])
def test_cli_rehashes_repo_local_verdict_closure(tmp_path: Path, tampered: str) -> None:
    contract_path, files = _write_verdict_repo(tmp_path)
    files[tampered].write_bytes(b"tampered")

    assert cli.main(["verify-contract", str(contract_path)]) == 2


def test_cli_rejects_well_formed_but_wrong_dvc_oid(tmp_path: Path) -> None:
    contract_path, _files = _write_verdict_repo(tmp_path)
    document = json.loads(contract_path.read_text(encoding="utf-8"))
    document["collections"][0]["dvc_oid"] = "md5:" + "0" * 32
    contract_path.write_text(canonical_json(document), encoding="utf-8")

    assert cli.main(["verify-contract", str(contract_path)]) == 2


def test_repository_file_verification_streams_without_whole_file_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"streaming-evidence" * 300_000
    evidence = tmp_path / "model.bin"
    evidence.write_bytes(payload)
    sha256 = hashlib.sha256(payload).hexdigest()
    dvc_oid = f"md5:{hashlib.md5(payload, usedforsecurity=False).hexdigest()}"

    def fail_whole_file_read(_path: Path) -> bytes:
        raise AssertionError("repository evidence must be hashed incrementally")

    monkeypatch.setattr(cli, "_read_pinned_regular_file", fail_whole_file_read)

    cli._verify_expected_repository_file(  # noqa: SLF001 - focused streaming boundary test.
        tmp_path,
        ("model.bin", len(payload), sha256, dvc_oid),
    )


@pytest.mark.parametrize("symlinked", ["input", "output", "code", "config", "lock"])
def test_cli_rejects_symlinked_verdict_closure(tmp_path: Path, symlinked: str) -> None:
    contract_path, files = _write_verdict_repo(tmp_path)
    original = files[symlinked]
    target = original.with_name(original.name + ".target")
    original.rename(target)
    original.symlink_to(target.name)

    assert cli.main(["verify-contract", str(contract_path)]) == 2


def test_cli_rejects_symlinked_contract(tmp_path: Path) -> None:
    contract_path, _files = _write_verdict_repo(tmp_path)
    target = contract_path.with_name("real.json")
    contract_path.rename(target)
    contract_path.symlink_to(target.name)

    assert cli.main(["verify-contract", str(contract_path)]) == 2
