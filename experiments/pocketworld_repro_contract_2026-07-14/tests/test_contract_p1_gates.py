from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from typing import TYPE_CHECKING

import pytest

from pocketworld_contract import cli
from pocketworld_contract.contract import validate_contract
from pocketworld_contract.manifest import ContractError, canonical_json

if TYPE_CHECKING:
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
                    "path": "scripts/run.py",
                    "sha256": "c" * 64,
                    "execution_status": "runnable",
                    "role": "verdict implementation",
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
            "status": "runnable",
            "path": "configs/run.json",
            "sha256": "f" * 64,
            "values": {"grid_m": 0.01},
        },
        "seeds": {"random_seed": 0, "deterministic": True, "notes": "fixed seed"},
        "command": {"status": "known", "argv": ["python", "scripts/run.py"], "cwd": "."},
        "metrics": {
            "definitions": [
                {"metric_id": "quality", "unit": "ratio", "direction": "higher_is_better"}
            ],
            "thresholds": [{"metric_id": "quality", "operator": ">=", "value": 0.9}],
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
        "pull_timestamp": "2026-07-14T00:00:00Z",
        "source_device_id": "fixture-device",
        "source_app_id": "com.kyle.PocketWorld",
        "source_app_revision": "fixture-app-revision",
        "source_capture_directory": "cap_1783933521157217",
        "ledger_capture_directory": "cap_1783933521157217",
        "source_quiescence_proven": False,
        "consistent_backup_proven": False,
        "atomic_db_wal_snapshot_proven": False,
        "capture_binding_proven": False,
        "integrity_check_passed": False,
        "db_pose_alignment_passed": False,
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
    return document


def _dependency(dependency_id: str, kind: str = "source_code") -> dict[str, object]:
    return {
        "dependency_id": dependency_id,
        "kind": kind,
        "source": "https://example.invalid/dependency",
        "revision": "v1",
        "license_identifier": "Apache-2.0",
        "license_evidence_sha256": "1" * 64,
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
        "dependencies": [_dependency("source-v1")],
        "reasons": [],
    }
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


def test_complete_typed_replay_contract_validates() -> None:
    document = _replay_verdict_contract()
    document["contract_id"] = "cap51-replay-fixture-v2"
    qualification = document["replay_qualification"]
    qualification["fixture_contract_id"] = document["contract_id"]
    for key in (
        "fresh_authorized_pull",
        "source_quiescence_proven",
        "atomic_db_wal_snapshot_proven",
        "capture_binding_proven",
        "integrity_check_passed",
        "db_pose_alignment_passed",
    ):
        qualification[key] = True
    document["artifacts"][0]["details"] = {}
    document["artifacts"][1]["replay_identity_included"] = False

    validate_contract(document)


@pytest.mark.parametrize(
    ("command", "raw"),
    [
        ("verify-contract", b'{"schema_version":1,"schema_version":1}\n'),
        ("gate-verdict", b'{"status":"verdict_eligible","status":"verdict_eligible"}\n'),
        ("verify-contract", b'{"schema_version":NaN}\n'),
        ("verify-contract", b'{"schema_version":Infinity}\n'),
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


def _write_verdict_repo(tmp_path: Path) -> tuple[Path, dict[str, Path]]:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
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

    document = _generic_verdict_contract()
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
    return contract_path, files


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
