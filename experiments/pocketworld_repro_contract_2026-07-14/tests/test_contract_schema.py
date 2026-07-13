from __future__ import annotations

import importlib
import importlib.resources
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pocketworld_contract.manifest import canonical_json, sha256_file

if TYPE_CHECKING:
    from types import ModuleType


REQUIRED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "contract_id",
    "status",
    "git",
    "upstream",
    "collections",
    "code",
    "environment",
    "models",
    "effective_config",
    "seeds",
    "command",
    "metrics",
    "exclusions",
    "stopping_rules",
    "artifacts",
    "deviations",
    "privacy",
    "product_qualification",
    "verdict",
}

ALLOWED_STATUSES = {
    "preserved_incomplete_feed",
    "provisional_not_verdict_eligible",
    "verdict_eligible",
    "invalid",
}

CONTRACTS_ROOT = Path(__file__).parents[1] / "contracts"
REPOSITORY_ROOT = Path(__file__).parents[3]

CAP50_MISSING_FEED_INPUTS = [
    "cell_102_slot_2_tap-335.jpg",
    "cell_91_slot_0_tap-364.jpg",
    "cell_91_slot_1_tap-370.jpg",
    "cell_91_slot_2_tap-374.jpg",
    "cell_91_slot_3_tap-379.jpg",
    "cell_75_slot_0_tap-394.jpg",
    "cell_75_slot_2_tap-407.jpg",
    "cell_75_slot_4_tap-425.jpg",
    "cell_75_slot_5_tap-431.jpg",
    "cell_91_slot_6_tap-471.jpg",
    "cell_91_slot_8_tap-484.jpg",
    "cell_91_slot_9_tap-490.jpg",
    "cell_91_slot_10_tap-495.jpg",
    "cell_91_slot_2_tap-511.jpg",
    "cell_90_slot_2_tap-521.jpg",
    "cell_90_slot_5_tap-552.jpg",
    "cell_90_slot_7_tap-571.jpg",
    "cell_91_slot_0_tap-1037.jpg",
    "cell_91_slot_6_tap-1058.jpg",
    "cell_91_slot_3_tap-1081.jpg",
    "cell_91_slot_2_tap-1093.jpg",
    "cell_91_slot_0_tap-1118.jpg",
    "cell_91_slot_6_tap-1132.jpg",
    "cell_91_slot_0_tap-1149.jpg",
]

CAP50_EXPECTED_ARTIFACT_HASHES = {
    "production-floor-ply": "3eaabe2b21c3d17116943ab0600e43901eaa76984b5bc15cef3d1d113f2ecb92",
    "floor-rescue-band-colored-ply": (
        "043536cc2b24fa23e8ebc8dd1121425cd02b1e7315893f8508078686db260130"
    ),
    "floor-planesweep-ply": "1113af4a446b9b2f7a3c624c2663134eb6afc1c748a8494bbdee9020d46cefab",
    "floor-maxed-colored-ply": "81dc1bc4814191d58cd30a46562be609598e6bee75e0b14cffb0b24551704514",
    "shell-cache-npz": "873fadcfa7b18f67dd66c164b7bddd4610775b87c8cf813a2c0e2a16dfa1219a",
    "fr-matches-npz": "ddbeeedc0da95da9193bf6bc1ab596f4456857a756be2aa6a8df51bbfea42660",
    "fr-matches-a-npz": "a94358e1a2cc2737bdd6b8f1640d98be12a5d8034980a7562fe1da832fa84189",
    "fr-matches-b-npz": "64e3449abf90fd38d2a2f0dc5dd65c1441236b98f09e506c2da93b3a7b3dc01a",
    "fr-matches-c-npz": "6186eb60ce97faf9e5f74761632285ca8b35e49b62ef7f2cf2484a3ea5c5b807",
    "fr-matches-d-npz": "76b55bcadcd6535b482dc220727767efe6959bc0fc1ab739ab6079eb57eeec83",
    "xsec-data-npz": "15aff75724a4140657262d6b6027fbb668dcedfede9e754646f4dfc130274667",
}

AXIS_FIELDS = {
    "license_status",
    "platform_qualification",
    "evidence_role",
    "lineage_contains_noncommercial",
}

COMMERCIAL_GATE_FIELDS = {"commercial_gate_included"}

NESTED_REQUIRED_FIELDS = [
    ("git", "repository"),
    ("git", "branch"),
    ("git", "commit"),
    ("git", "dirty_diff_sha256"),
    ("upstream", "producer_stack"),
    ("upstream", "consumer_target_stack"),
    ("upstream/producer_stack", "identity"),
    ("upstream/producer_stack", "revision"),
    ("upstream/producer_stack", "colmap_version"),
    ("upstream/producer_stack", "ceres_version"),
    ("upstream/consumer_target_stack", "identity"),
    ("upstream/consumer_target_stack", "revision"),
    ("upstream/consumer_target_stack", "colmap_version"),
    ("upstream/consumer_target_stack", "ceres_version"),
    ("code", "entries"),
    ("environment", "producer"),
    ("environment", "verifier"),
    ("environment/producer", "python_version"),
    ("environment/producer", "uv_lock_sha256"),
    ("environment/producer", "hardware"),
    ("environment/producer", "backend"),
    ("environment/verifier", "python_version"),
    ("environment/verifier", "numpy_version"),
    ("environment/verifier", "uv_lock_sha256"),
    ("environment/verifier", "hardware"),
    ("environment/verifier", "backend"),
    ("effective_config", "status"),
    ("effective_config", "path"),
    ("effective_config", "sha256"),
    ("effective_config", "values"),
    ("seeds", "random_seed"),
    ("seeds", "deterministic"),
    ("seeds", "notes"),
    ("command", "status"),
    ("command", "argv"),
    ("command", "cwd"),
    ("metrics", "definitions"),
    ("metrics", "thresholds"),
    ("metrics", "observed"),
    ("privacy", "classification"),
    ("privacy", "storage"),
    ("privacy", "remote_allowed"),
    ("privacy", "same_disk_only"),
    ("privacy", "constraints"),
    ("product_qualification", "status"),
    ("product_qualification", "commercial_open_source_dependencies_verified"),
    ("product_qualification", "dependencies"),
    ("product_qualification", "reasons"),
]


def _contract_module() -> ModuleType:
    return importlib.import_module("pocketworld_contract.contract")


def _load_contract(filename: str) -> dict[str, object]:
    return json.loads((CONTRACTS_ROOT / filename).read_text(encoding="utf-8"))


def _evidence_by_id(document: dict[str, object]) -> dict[str, dict[str, object]]:
    evidence = [*document["collections"], *document["artifacts"]]
    return {item["evidence_id"]: item for item in evidence}


def _minimal_contract() -> dict[str, object]:
    return {
        "schema_version": 1,
        "contract_id": "fixture-v1",
        "status": "verdict_eligible",
        "git": {
            "repository": ".",
            "branch": "fixture",
            "commit": "a" * 40,
            "dirty_diff_sha256": "b" * 64,
        },
        "upstream": {
            "producer_stack": {
                "identity": "fixture historical producer",
                "revision": "fixture-producer-v1",
                "colmap_version": "4.0.4",
                "ceres_version": "2.2",
            },
            "consumer_target_stack": {
                "identity": "PocketWorld target policy",
                "revision": "fixture-target-v1",
                "colmap_version": "4.1.0",
                "ceres_version": "2.2-submodule",
            },
        },
        "collections": [],
        "code": {"entries": []},
        "environment": {
            "producer": {
                "python_version": "3.11",
                "uv_lock_sha256": "c" * 64,
                "hardware": "fixture",
                "backend": "cpu",
            },
            "verifier": {
                "python_version": "3.11",
                "numpy_version": "2.4.2",
                "uv_lock_sha256": "f" * 64,
                "hardware": "fixture",
                "backend": "cpu",
            },
        },
        "models": [],
        "effective_config": {
            "status": "runnable",
            "path": "configs/fixture.json",
            "sha256": "d" * 64,
            "values": {"grid_m": 0.01},
        },
        "seeds": {"random_seed": 0, "deterministic": True, "notes": "fixture seed"},
        "command": {
            "status": "known",
            "argv": ["python", "scripts/run.py", "--config", "configs/fixture.json"],
            "cwd": ".",
        },
        "metrics": {"definitions": [], "thresholds": [], "observed": []},
        "exclusions": [],
        "stopping_rules": [],
        "artifacts": [],
        "deviations": [],
        "privacy": {
            "classification": "private_indoor_capture",
            "storage": "encrypted_local_mac",
            "remote_allowed": False,
            "same_disk_only": True,
            "constraints": ["no remote transfer"],
        },
        "product_qualification": {
            "status": "commercial_evaluation_candidate",
            "commercial_open_source_dependencies_verified": True,
            "dependencies": [
                {
                    "dependency_id": "fixture-dependency",
                    "kind": "source_code",
                    "source": "https://example.invalid/fixture",
                    "revision": "v1.0.0",
                    "license_identifier": "Apache-2.0",
                    "license_evidence_sha256": "1" * 64,
                    "license_status": "verified_commercial_open_source",
                    "lineage_contains_noncommercial": False,
                    "noncommercial_lineage_sources": [],
                }
            ],
            "reasons": [],
        },
        "verdict": {"eligible": True, "decision": "fixture_pass", "blockers": []},
    }


def _evidence_item() -> dict[str, object]:
    return {
        "evidence_id": "fixture-artifact",
        "identity_status": "preserved",
        "path": "artifacts/fixture.bin",
        "bytes": 7,
        "sha256": "e" * 64,
        "dvc_oid": "md5:0123456789abcdef0123456789abcdef",
        "producer": "fixture producer",
        "consumer": "fixture consumer",
        "inclusion_reason": "fixture evidence",
        "license_status": "user_owned_private_input",
        "platform_qualification": "mac_only",
        "evidence_role": "diagnostic",
        "lineage_contains_noncommercial": False,
        "noncommercial_lineage_sources": [],
        "commercial_gate_included": False,
        "commercial_gate_exclusion_reason": "Private inputs are not open-source dependencies.",
        "details": {},
    }


@pytest.mark.parametrize("missing_field", sorted(REQUIRED_TOP_LEVEL_FIELDS))
def test_validate_contract_requires_the_full_truth_surface(missing_field: str) -> None:
    contract = _contract_module()
    document = _minimal_contract()
    del document[missing_field]

    with pytest.raises(contract.ContractError, match=missing_field):
        contract.validate_contract(document)


def test_packaged_schema_resource_matches_versioned_schema() -> None:
    versioned_schema = Path(__file__).parents[1] / "schemas" / "contract-v1.schema.json"
    packaged_schema = importlib.resources.files("pocketworld_contract").joinpath(
        "schemas/contract-v1.schema.json"
    )

    assert packaged_schema.read_bytes() == versioned_schema.read_bytes()


def test_validator_loads_schema_through_package_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _contract_module()
    original_files = importlib.resources.files
    calls: list[str] = []

    def tracked_files(anchor: str) -> object:
        calls.append(anchor)
        return original_files(anchor)

    monkeypatch.setattr(contract, "resource_files", tracked_files, raising=False)
    contract._validator.cache_clear()  # noqa: SLF001 - cache behavior is the test subject.
    try:
        contract.validate_contract(_minimal_contract())
    finally:
        contract._validator.cache_clear()  # noqa: SLF001 - restore isolated cache state.

    assert calls == ["pocketworld_contract"]


def test_validate_contract_rejects_status_outside_closed_vocabulary() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["status"] = "complete"

    with pytest.raises(contract.ContractError, match="status"):
        contract.validate_contract(document)


@pytest.mark.parametrize("missing_axis", sorted(AXIS_FIELDS))
def test_every_evidence_item_requires_four_independent_axes(missing_axis: str) -> None:
    contract = _contract_module()
    document = _minimal_contract()
    item = _evidence_item()
    del item[missing_axis]
    document["artifacts"] = [item]

    with pytest.raises(contract.ContractError, match=missing_axis):
        contract.validate_contract(document)


def test_null_truth_requires_an_exact_structured_deviation() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["status"] = "provisional_not_verdict_eligible"
    document["verdict"] = {
        "eligible": False,
        "decision": "blocked",
        "blockers": ["historical command is unknown"],
    }
    document["seeds"]["random_seed"] = None

    with pytest.raises(contract.ContractError, match=r"/seeds/random_seed"):
        contract.validate_contract(document)

    document["deviations"] = [
        {
            "deviation_id": "missing-historical-command",
            "field": "/seeds/random_seed",
            "reason": "The historical random seed was not recorded.",
            "blocks_verdict": True,
            "resolution": "Recover an immutable command record or rerun cleanly.",
        }
    ]
    contract.validate_contract(document)


def test_unknown_placeholder_must_be_null_not_an_optimistic_string() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["git"]["branch"] = "unknown"

    with pytest.raises(contract.ContractError, match=r"/git/branch"):
        contract.validate_contract(document)


def test_not_recorded_command_uses_nulls_with_deviations() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["status"] = "provisional_not_verdict_eligible"
    document["command"] = {"status": "not_recorded", "argv": None, "cwd": None}
    document["deviations"] = [
        {
            "deviation_id": "historical-command-argv-not-recorded",
            "field": "/command/argv",
            "reason": "Historical argv was not recorded.",
            "blocks_verdict": True,
            "resolution": "Perform a clean rerun with a canonical argv.",
        },
        {
            "deviation_id": "historical-command-cwd-not-recorded",
            "field": "/command/cwd",
            "reason": "Historical working directory was not recorded.",
            "blocks_verdict": True,
            "resolution": "Perform a clean rerun with a repository-relative cwd.",
        },
    ]
    document["verdict"] = {
        "eligible": False,
        "decision": "blocked",
        "blockers": ["historical command not recorded"],
    }

    contract.validate_contract(document)


def test_verdict_eligible_rejects_blocking_deviation_even_without_null() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["deviations"] = [
        {
            "deviation_id": "unresolved-control-variable",
            "field": "/command",
            "reason": "The command requires independent confirmation.",
            "blocks_verdict": True,
            "resolution": "Confirm the exact command before a verdict.",
        }
    ]

    with pytest.raises(contract.ContractError, match=r"verdict|blocking"):
        contract.validate_contract(document)


def test_private_capture_input_has_a_distinct_license_class() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["artifacts"] = [_evidence_item()]

    contract.validate_contract(document)


@pytest.mark.parametrize("missing_field", sorted(COMMERCIAL_GATE_FIELDS))
def test_evidence_requires_an_explicit_commercial_gate_decision(missing_field: str) -> None:
    contract = _contract_module()
    document = _minimal_contract()
    item = _evidence_item()
    del item[missing_field]
    document["artifacts"] = [item]

    with pytest.raises(contract.ContractError, match=missing_field):
        contract.validate_contract(document)


def test_excluded_evidence_requires_a_nonempty_exclusion_reason() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    item = _evidence_item()
    del item["commercial_gate_exclusion_reason"]
    document["artifacts"] = [item]

    with pytest.raises(contract.ContractError, match="commercial_gate_exclusion_reason"):
        contract.validate_contract(document)


def test_included_verified_dependency_omits_exclusion_reason() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    item = _evidence_item()
    item.update(
        {
            "license_status": "verified_commercial_open_source",
            "evidence_role": "open_source_dependency",
            "commercial_gate_included": True,
        }
    )
    del item["commercial_gate_exclusion_reason"]
    document["artifacts"] = [item]

    contract.validate_contract(document)


@pytest.mark.parametrize(
    ("license_status", "contains_noncommercial"),
    [
        ("user_owned_private_input", False),
        ("unknown_pending_audit", False),
        ("noncommercial_ineligible", True),
        ("verified_commercial_open_source", True),
    ],
)
def test_commercial_gate_inclusion_requires_clean_verified_open_source(
    license_status: str,
    contains_noncommercial: bool,  # noqa: FBT001 - pytest supplies this Boolean axis.
) -> None:
    contract = _contract_module()
    document = _minimal_contract()
    item = _evidence_item()
    item.update(
        {
            "license_status": license_status,
            "lineage_contains_noncommercial": contains_noncommercial,
            "noncommercial_lineage_sources": (
                ["LoFTR-indoor/ScanNet"] if contains_noncommercial else []
            ),
            "commercial_gate_included": True,
        }
    )
    del item["commercial_gate_exclusion_reason"]
    document["artifacts"] = [item]

    with pytest.raises(contract.ContractError, match=r"commercial|open.source|lineage"):
        contract.validate_contract(document)


def test_noncommercial_upper_bound_can_only_be_excluded_with_a_reason() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    item = _evidence_item()
    item.update(
        {
            "license_status": "noncommercial_ineligible",
            "evidence_role": "research_upper_bound",
            "lineage_contains_noncommercial": True,
            "noncommercial_lineage_sources": ["LoFTR-indoor/ScanNet"],
            "commercial_gate_included": False,
            "commercial_gate_exclusion_reason": (
                "Excluded noncommercial research upper bound; never product evidence."
            ),
        }
    )
    document["artifacts"] = [item]

    contract.validate_contract(document)


@pytest.mark.parametrize("unknown_axis", sorted(AXIS_FIELDS))
def test_unknown_evidence_axis_is_null_with_exact_deviation(unknown_axis: str) -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["status"] = "preserved_incomplete_feed"
    item = _evidence_item()
    item[unknown_axis] = None
    if unknown_axis == "lineage_contains_noncommercial":
        item["noncommercial_lineage_sources"] = []
    document["artifacts"] = [item]
    document["deviations"] = [
        {
            "deviation_id": f"unknown-{unknown_axis}",
            "field": f"/artifacts/0/{unknown_axis}",
            "reason": "The source evidence does not establish this axis.",
            "blocks_verdict": True,
            "resolution": "Audit the original producer and immutable evidence.",
        }
    ]
    document["verdict"] = {
        "eligible": False,
        "decision": "preservation_only",
        "blockers": [f"unknown {unknown_axis}"],
    }

    contract.validate_contract(document)


def test_commercial_candidate_rejects_empty_dependency_evidence() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["product_qualification"]["dependencies"] = []

    with pytest.raises(contract.ContractError, match=r"dependenc"):
        contract.validate_contract(document)


def test_commercial_candidate_rejects_unverified_dependency_license() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    dependency = document["product_qualification"]["dependencies"][0]
    dependency["license_status"] = "unknown_pending_audit"

    with pytest.raises(contract.ContractError, match=r"dependenc|license"):
        contract.validate_contract(document)


def test_commercial_candidate_rejects_unknown_dependency_lineage() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    dependency = document["product_qualification"]["dependencies"][0]
    dependency["lineage_contains_noncommercial"] = None
    document["deviations"] = [
        {
            "deviation_id": "dependency-lineage-not-proven",
            "field": "/product_qualification/dependencies/0/lineage_contains_noncommercial",
            "reason": "The dependency lineage audit is incomplete.",
            "blocks_verdict": True,
            "resolution": "Complete the dependency lineage audit.",
        }
    ]
    document["status"] = "provisional_not_verdict_eligible"
    document["verdict"] = {
        "eligible": False,
        "decision": "blocked",
        "blockers": ["dependency lineage is not proven"],
    }

    with pytest.raises(contract.ContractError, match=r"dependenc|lineage"):
        contract.validate_contract(document)


def test_commercial_candidate_rejects_model_without_immutable_identity() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["models"] = [
        {
            "model_id": "fixture-model",
            "source": None,
            "revision": None,
            "weights_sha256": None,
            "license_evidence_sha256": None,
            "license_status": "verified_commercial_open_source",
            "usage": "fixture inference",
        }
    ]
    document["deviations"] = [
        {
            "deviation_id": f"model-{field}-not-bound",
            "field": f"/models/0/{field}",
            "reason": "The model identity is incomplete.",
            "blocks_verdict": True,
            "resolution": "Bind immutable model identity before qualification.",
        }
        for field in ("source", "revision", "weights_sha256", "license_evidence_sha256")
    ]
    document["status"] = "provisional_not_verdict_eligible"
    document["verdict"] = {
        "eligible": False,
        "decision": "blocked",
        "blockers": ["model identity is incomplete"],
    }

    with pytest.raises(contract.ContractError, match=r"model|identity|source|revision|weight"):
        contract.validate_contract(document)


def test_model_requires_immutable_license_evidence_hash() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["models"] = [
        {
            "model_id": "fixture-model",
            "source": "https://example.invalid/model",
            "revision": "v1",
            "weights_sha256": "2" * 64,
            "license_status": "verified_commercial_open_source",
            "usage": "fixture inference",
        }
    ]

    with pytest.raises(contract.ContractError, match=r"license_evidence_sha256"):
        contract.validate_contract(document)


def test_product_dependency_noncommercial_lineage_requires_named_sources() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["product_qualification"]["status"] = "not_qualified"
    document["product_qualification"]["commercial_open_source_dependencies_verified"] = False
    dependency = document["product_qualification"]["dependencies"][0]
    dependency["license_status"] = "noncommercial_ineligible"
    dependency["lineage_contains_noncommercial"] = True

    with pytest.raises(contract.ContractError, match=r"lineage|source"):
        contract.validate_contract(document)


def test_product_dependency_can_name_noncommercial_lineage_source() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["status"] = "preserved_incomplete_feed"
    document["verdict"] = {
        "eligible": False,
        "decision": "preservation_only",
        "blockers": ["noncommercial dependency"],
    }
    document["product_qualification"]["status"] = "not_qualified"
    document["product_qualification"]["commercial_open_source_dependencies_verified"] = False
    dependency = document["product_qualification"]["dependencies"][0]
    dependency.update(
        {
            "license_status": "noncommercial_ineligible",
            "lineage_contains_noncommercial": True,
            "noncommercial_lineage_sources": ["LoFTR-indoor/ScanNet"],
        }
    )

    contract.validate_contract(document)


@pytest.mark.parametrize(
    ("object_path", "missing_field"),
    NESTED_REQUIRED_FIELDS,
    ids=[f"{path}/{field}" for path, field in NESTED_REQUIRED_FIELDS],
)
def test_nested_truth_surfaces_reject_missing_fields(
    object_path: str,
    missing_field: str,
) -> None:
    contract = _contract_module()
    document = _minimal_contract()
    target = document
    for component in object_path.split("/"):
        target = target[component]
    del target[missing_field]

    with pytest.raises(contract.ContractError, match=missing_field):
        contract.validate_contract(document)


@pytest.mark.parametrize(
    "transient_path",
    [
        "/private/tmp/volatile/config.json",
        "/var/mobile/Containers/Data/Application/UUID/config.json",
        "/private/var/mobile/Containers/Data/Application/UUID/config.json",
    ],
)
def test_runnable_effective_config_rejects_transient_absolute_paths(
    transient_path: str,
) -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["effective_config"]["values"] = {"input_path": transient_path}

    with pytest.raises(contract.ContractError, match=r"effective_config|transient|path"):
        contract.validate_contract(document)


def test_historical_evidence_can_retain_raw_transient_path_for_audit() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["status"] = "preserved_incomplete_feed"
    document["effective_config"].update(
        {
            "status": "evidence_source_not_runnable",
            "path": "/private/tmp/historical/effective-config.json",
            "values": {"historical_input": "/private/tmp/historical/input"},
        }
    )
    document["verdict"] = {
        "eligible": False,
        "decision": "preservation_only",
        "blockers": ["historical configuration is not directly runnable"],
    }

    contract.validate_contract(document)


def test_known_command_rejects_mobile_container_path() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["command"]["argv"].append("/var/mobile/Containers/Data/Application/UUID/input.json")

    with pytest.raises(contract.ContractError, match=r"command|mobile|transient"):
        contract.validate_contract(document)


def test_runnable_config_path_must_be_repository_relative() -> None:
    contract = _contract_module()
    document = _minimal_contract()
    document["effective_config"]["path"] = "../outside.json"

    with pytest.raises(contract.ContractError, match=r"effective_config|relative|path"):
        contract.validate_contract(document)


def test_cap50_contract_is_canonical_and_validates_fail_closed() -> None:
    contract = _contract_module()
    path = CONTRACTS_ROOT / "cap50-floor-plane-sweep-v1.json"
    document = _load_contract(path.name)

    assert path.read_text(encoding="utf-8") == canonical_json(document)
    contract.validate_contract(document)
    assert document["contract_id"] == "cap50-floor-plane-sweep-v1"
    assert document["status"] == "preserved_incomplete_feed"
    assert document["upstream"]["consumer_target_stack"]["colmap_version"] == "4.1.0"
    assert document["upstream"]["consumer_target_stack"]["ceres_version"] == ("2.2-submodule")
    assert document["upstream"]["producer_stack"]["colmap_version"] is None
    assert document["effective_config"]["values"]["grid_m"] == 0.01
    assert document["verdict"]["eligible"] is False


def test_cap50_contract_preserves_exact_139_115_24_closure() -> None:
    document = _load_contract("cap50-floor-plane-sweep-v1.json")
    evidence = _evidence_by_id(document)
    closure = evidence["cap50-selected-feed-closure"]["details"]

    assert closure["live_feed_count"] == 139
    assert closure["selected_input_count"] == 115
    assert closure["missing_input_count"] == 24
    assert closure["missing_input_names"] == CAP50_MISSING_FEED_INPUTS
    assert closure["set_difference_rule"] == (
        "live-feed image basenames minus raw-selected JPEG basenames"
    )
    assert closure["live_feed_sha256"] == (
        "d3970be1d4f152b605525b75e4495d2c14c2b17138617ed94fca19711cc1603b"
    )
    assert closure["selected_manifest_sha256"] == (
        "4288a756f80a49a12f8da520b564a3a4a856ac4949540b2ab50bebb671f6a0ad"
    )
    assert evidence["cap50-raw-selected-115-manifest"]["sha256"] == (
        "4288a756f80a49a12f8da520b564a3a4a856ac4949540b2ab50bebb671f6a0ad"
    )
    assert evidence["cap50-work-png-115-manifest"]["sha256"] == (
        "ca9ed3bafdc2a479769b553268a2eb8e8ee322d238b88997ffc428899d4d5ad4"
    )
    raw_axes = evidence["cap50-raw-selected-115-manifest"]["details"]["manifest_asset_axes"]
    assert raw_axes == {
        "evidence_role": "raw-capture-input-and-sidecar",
        "license_status": "user-owned-capture-local-research",
        "lineage_contains_noncommercial": False,
        "normalized_contract_license_status": "user_owned_private_input",
        "platform_qualification": "historical-ios-capture-mac-research-input",
    }
    png_axes = evidence["cap50-work-png-115-manifest"]["details"]["manifest_asset_axes"]
    assert png_axes == {
        "evidence_role": "exact-preprocessed-input",
        "license_status": "user-owned-derived-capture-local-research",
        "lineage_contains_noncommercial": False,
        "normalized_contract_license_status": "user_owned_private_input",
        "platform_qualification": "historical-mac-preprocessed-evidence-only",
    }


def test_cap50_contract_pins_requested_outputs_and_all_seven_npz_hashes() -> None:
    document = _load_contract("cap50-floor-plane-sweep-v1.json")
    evidence = _evidence_by_id(document)

    for evidence_id, expected_sha256 in CAP50_EXPECTED_ARTIFACT_HASHES.items():
        assert evidence[evidence_id]["sha256"] == expected_sha256
    assert evidence["production-floor-ply"]["details"]["vertex_count"] == 5845
    assert evidence["floor-rescue-band-colored-ply"]["details"]["vertex_count"] == 1435
    assert evidence["floor-planesweep-ply"]["details"]["vertex_count"] == 12672
    assert evidence["floor-maxed-colored-ply"]["details"]["vertex_count"] == 18222


def test_cap50_contract_does_not_invent_dvc_or_commercial_qualification() -> None:
    document = _load_contract("cap50-floor-plane-sweep-v1.json")
    evidence = [*document["collections"], *document["artifacts"]]
    deviation_fields = {item["field"] for item in document["deviations"]}

    for section in ("collections", "artifacts"):
        for index, item in enumerate(document[section]):
            if item["dvc_oid"] is None:
                assert f"/{section}/{index}/dvc_oid" in deviation_fields
    assert document["product_qualification"]["status"] == "not_qualified"
    assert (
        document["product_qualification"]["commercial_open_source_dependencies_verified"] is False
    )
    assert all(item["commercial_gate_included"] is False for item in evidence)


def test_cap50_license_and_lineage_boundaries_are_explicit() -> None:
    document = _load_contract("cap50-floor-plane-sweep-v1.json")
    evidence = _evidence_by_id(document)

    pure_a = evidence["floor-planesweep-ply"]
    assert pure_a["license_status"] == "unknown_pending_audit"
    assert pure_a["platform_qualification"] == "mac_only"
    assert pure_a["lineage_contains_noncommercial"] is True
    assert pure_a["noncommercial_lineage_sources"] == ["LoFTR-indoor/ScanNet"]
    assert pure_a["commercial_gate_included"] is False

    for evidence_id in (
        "floor-rescue-band-colored-ply",
        "floor-maxed-colored-ply",
        "fr-matches-b-npz",
        "fr-matches-c-npz",
        "fr-matches-d-npz",
    ):
        item = evidence[evidence_id]
        assert item["license_status"] == "noncommercial_ineligible"
        assert item["lineage_contains_noncommercial"] is True
        assert item["commercial_gate_included"] is False

    for evidence_id in ("production-floor-ply", "shell-cache-npz", "xsec-data-npz"):
        item = evidence[evidence_id]
        assert item["license_status"] is None
        assert item["lineage_contains_noncommercial"] is None


def test_cap50_contract_reverifies_every_referenced_git_file() -> None:
    document = _load_contract("cap50-floor-plane-sweep-v1.json")
    evidence = _evidence_by_id(document)

    for evidence_id in (
        "cap50-selected-feed-closure",
        "cap50-raw-selected-115-manifest",
        "cap50-work-png-115-manifest",
        "cap50-poses-json",
        "cap50-floor-frame-ids-json",
    ):
        item = evidence[evidence_id]
        path = REPOSITORY_ROOT / item["path"]
        assert path.is_file(), evidence_id
        assert path.stat().st_size == item["bytes"], evidence_id
        assert sha256_file(path) == item["sha256"], evidence_id

    for entry in document["code"]["entries"]:
        path = REPOSITORY_ROOT / entry["path"]
        assert path.is_file(), entry["path"]
        assert sha256_file(path) == entry["sha256"], entry["path"]

    config = document["effective_config"]
    config_path = CONTRACTS_ROOT.parent / config["path"]
    assert config_path.is_file()
    assert sha256_file(config_path) == config["sha256"]
