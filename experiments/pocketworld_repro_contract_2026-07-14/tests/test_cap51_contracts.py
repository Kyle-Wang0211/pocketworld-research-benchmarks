from __future__ import annotations

import json
from pathlib import Path

from pocketworld_contract.contract import validate_contract
from pocketworld_contract.manifest import canonical_json

CONTRACTS_ROOT = Path(__file__).parents[1] / "contracts"
ARCHIVE_NAME = "cap51-capture-archive-provisional-v1.json"
FIXTURE_NAME = "cap51-incremental-ba-fixture-provisional-v1.json"


def _load(name: str) -> tuple[Path, dict[str, object]]:
    path = CONTRACTS_ROOT / name
    return path, json.loads(path.read_text(encoding="utf-8"))


def _evidence_by_id(document: dict[str, object]) -> dict[str, dict[str, object]]:
    evidence = [*document["collections"], *document["artifacts"]]
    return {item["evidence_id"]: item for item in evidence}


def _deviation_fields(document: dict[str, object]) -> set[str]:
    return {item["field"] for item in document["deviations"]}


def test_cap51_contracts_are_canonical_and_validate_fail_closed() -> None:
    for name, contract_id in (
        (ARCHIVE_NAME, "cap51-capture-archive-provisional-v1"),
        (FIXTURE_NAME, "cap51-incremental-ba-fixture-provisional-v1"),
    ):
        path, document = _load(name)

        assert path.read_text(encoding="utf-8") == canonical_json(document)
        validate_contract(document)
        assert document["contract_id"] == contract_id
        assert document["status"] == "provisional_not_verdict_eligible"
        assert document["validation_scope"] in {
            "preservation_record",
            "provisional_fixture",
        }
        assert document["verdict"]["eligible"] is False
        assert document["upstream"]["producer_stack"] == {
            "ceres_version": None,
            "colmap_version": None,
            "identity": None,
            "revision": None,
        }
        assert document["upstream"]["consumer_target_stack"]["colmap_version"] == ("4.1.0")
        assert document["upstream"]["consumer_target_stack"]["ceres_version"] == ("2.2-submodule")


def test_cap51_archive_records_the_photo_gap_without_deciding_replay() -> None:
    _path, document = _load(ARCHIVE_NAME)
    evidence = _evidence_by_id(document)
    photo_gap = evidence["cap51-missing-photo-archive"]

    assert photo_gap["bytes"] == 0
    assert photo_gap["sha256"] is None
    assert photo_gap["identity_status"] == "missing"
    assert photo_gap["details"] == {
        "available_images": 0,
        "expected_frame_id_max": 104,
        "expected_frame_id_min": 0,
        "expected_images": 105,
        "missing_images": 105,
        "replay_eligibility_effect": "none",
    }
    assert document["verdict"]["decision"] == (
        "capture_archive_incomplete_replay_eligibility_not_assessed"
    )
    assert any(
        "photo absence" in item["rule"].casefold() and "replay" in item["rule"].casefold()
        for item in document["exclusions"]
    )


def test_cap51_archive_pins_feed_bundle_and_sparse_evidence() -> None:
    _path, document = _load(ARCHIVE_NAME)
    evidence = _evidence_by_id(document)

    assert evidence["cap51-feed-ledger"]["bytes"] == 63442
    assert evidence["cap51-feed-ledger"]["sha256"] == (
        "d86ac0c44a9e5ae154f286cc9fc6baf215f949c5335b4bf9210e87c6d018770c"
    )
    assert evidence["cap51-feed-ledger"]["details"] == {
        "capture_binding_proven": False,
        "complete_pose_fields": True,
        "frame_id_contiguous": True,
        "frame_id_max": 104,
        "frame_id_min": 0,
        "ledger_capture_directory": "cap_1783933521157217",
        "pose_record_count": 105,
    }
    assert evidence["cap51-photo-bundle"]["bytes"] == 164416
    assert evidence["cap51-photo-bundle"]["sha256"] == (
        "e2a6c57b215ad1641e73c76b0adcaba8f6c77f563c70ea62c17ca15a55743caf"
    )
    assert evidence["cap51-photo-bundle"]["details"]["selected_frame_count"] == 81
    assert evidence["cap51-sparse-ply"]["bytes"] == 966125
    assert evidence["cap51-sparse-ply"]["sha256"] == (
        "fb2db1e1ee89692ed47b0bd3d38773fc42f37ecb94ccd485fc7a1952b13fe3f7"
    )


def test_cap51_fixture_pins_db_wal_pose_and_clone_only_integrity() -> None:
    _path, document = _load(FIXTURE_NAME)
    evidence = _evidence_by_id(document)
    database = evidence["cap51-replay-db"]
    feed = evidence["cap51-replay-pose-ledger"]
    wal = evidence["cap51-replay-wal"]

    assert database["bytes"] == 134975488
    assert database["sha256"] == (
        "af1bd571d81cf27228e6b1bd8faa9617a1734bf0d32c1c67ec849c4bc7f5ba97"
    )
    assert database["details"] == {
        "descriptor_row_count": 105,
        "image_count": 105,
        "image_id_contiguous": True,
        "image_id_max": 105,
        "image_id_min": 1,
        "integrity_check": "ok",
        "integrity_check_scope": "existing_read_only_clone_only",
        "keypoint_row_count": 105,
        "planned_fresh_pull_app_identifier": "com.kyle.PocketWorld",
        "planned_fresh_pull_device_id": "1B290474-D354-5B4C-AAB0-0805AC5DC832",
    }
    assert database["details"]["planned_fresh_pull_device_id"] == (
        "1B290474-D354-5B4C-AAB0-0805AC5DC832"
    )
    assert database["details"]["planned_fresh_pull_app_identifier"] == ("com.kyle.PocketWorld")
    qualification = document["replay_qualification"]
    assert document["contract_kind"] == "replay_fixture"
    assert qualification["fresh_authorized_pull"] is False
    assert qualification["capture_binding_proven"] is False
    assert qualification["source_app_revision"] is None
    assert qualification["source_quiescence_proven"] is False
    assert qualification["consistent_backup_proven"] is False
    assert qualification["atomic_db_wal_snapshot_proven"] is False
    assert qualification["integrity_check_passed"] is False
    assert qualification["db_pose_alignment_passed"] is False
    assert database["replay_identity_included"] is True
    assert wal["bytes"] == 4152
    assert wal["sha256"] == ("4cda3e63ad1604ac94724ee4f24327ee4fec7d86fa97056edca25ea76d85fa72")
    assert wal["replay_identity_included"] is True
    assert feed["bytes"] == 63442
    assert feed["sha256"] == ("d86ac0c44a9e5ae154f286cc9fc6baf215f949c5335b4bf9210e87c6d018770c")
    assert feed["details"] == {
        "complete_pose_fields": True,
        "db_image_id_equals_pose_frame_id_plus_one": True,
        "frame_id_contiguous": True,
        "frame_id_max": 104,
        "frame_id_min": 0,
        "pose_record_count": 105,
    }
    assert feed["replay_identity_included"] is True
    assert qualification["ledger_capture_directory"] == "cap_1783933521157217"


def test_cap51_fixture_excludes_volatile_shm_from_replay_identity() -> None:
    _path, document = _load(FIXTURE_NAME)
    evidence = _evidence_by_id(document)
    shm = evidence["cap51-replay-shm-drift"]

    assert shm["identity_status"] == "excluded_volatile"
    assert shm["bytes"] == 32768
    assert shm["sha256"] == ("7f2ab24bea9c7734ce7397f9b1c8b985a9a7d46bf65985a1b70effec19680c64")
    assert shm["details"]["previous_observed_sha256"] == (
        "4378012510ee558e6863a5d184315967f667a5695e1945bab16eca4b08082eeb"
    )
    assert shm["replay_identity_included"] is False
    assert shm["details"]["cause"] is None
    assert "/artifacts/0/details/cause" in _deviation_fields(document)

    identity_ids = {
        item["evidence_id"]
        for item in [*document["collections"], *document["artifacts"]]
        if item["replay_identity_included"] is True
    }
    assert identity_ids == {
        "cap51-replay-db",
        "cap51-replay-pose-ledger",
        "cap51-replay-wal",
    }


def test_cap51_fixture_gate_remains_closed_for_every_identity_blocker() -> None:
    _path, document = _load(FIXTURE_NAME)
    blockers = set(document["verdict"]["blockers"])

    assert {
        "No fresh user-authorized device pull is recorded.",
        "Producer quiescence is not proven.",
        "The DB/WAL pair is not proven to be an atomic SQLite snapshot.",
        "The DB/pose pair is not bound to the same cap51 capture directory.",
        "The source PocketWorld app revision is not proven.",
    } <= blockers
    assert all("photo" not in blocker.casefold() for blocker in blockers)
    assert document["verdict"]["decision"] == ("blocked_pending_fresh_capture_bound_quiescent_pull")


def test_cap51_evidence_is_never_used_as_commercial_gate_evidence() -> None:
    for name in (ARCHIVE_NAME, FIXTURE_NAME):
        _path, document = _load(name)
        deviation_fields = _deviation_fields(document)

        for section in ("collections", "artifacts"):
            for index, item in enumerate(document[section]):
                assert item["commercial_gate_included"] is False
                assert item["commercial_gate_exclusion_reason"]
                assert item["dvc_oid"] is None
                assert f"/{section}/{index}/dvc_oid" in deviation_fields
                for axis in (
                    "license_status",
                    "platform_qualification",
                    "evidence_role",
                    "lineage_contains_noncommercial",
                ):
                    if item[axis] is None:
                        assert f"/{section}/{index}/{axis}" in deviation_fields
