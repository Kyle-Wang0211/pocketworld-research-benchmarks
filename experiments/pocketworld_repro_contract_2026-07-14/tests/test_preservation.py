from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from pocketworld_contract.preservation import (
    CLONE_FLAGS,
    BatchMapError,
    CloneFileError,
    CloneVerification,
    ResourceSnapshot,
    ResourceSnapshotError,
    clonefile_regular,
    evaluate_resource_gate,
    find_forbidden_git_paths,
    parse_resource_snapshot,
    required_disk_bytes,
    validate_batch_map,
)

EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = EXPERIMENT_ROOT.parents[1]
BATCH_MAP_PATH = EXPERIMENT_ROOT / "contracts" / "resource-batches-v1.json"
INVENTORY_PATH = (
    REPOSITORY_ROOT
    / "openspec"
    / "changes"
    / "freeze-pocketworld-research-contract"
    / "evidence"
    / "pre-copy-evidence-inventory.json"
)
GIB = 1024**3
MIB = 1024**2


def _load_batch_map() -> dict[str, object]:
    return json.loads(BATCH_MAP_PATH.read_text(encoding="utf-8"))


def _git_check_ignored(path: str) -> bool:
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(  # noqa: S603
        [git, "-C", str(REPOSITORY_ROOT), "check-ignore", "--no-index", "-q", "--", path],
        check=False,
    )
    assert result.returncode in {0, 1}
    return result.returncode == 0


def test_required_disk_uses_fixed_headroom_and_double_batch_bytes() -> None:
    assert required_disk_bytes(205_162_291) == (15 * GIB) + (2 * 205_162_291) + (256 * MIB)


def test_committed_batch_map_is_strict_and_sums_fourteen_unique_batches() -> None:
    document = _load_batch_map()

    validate_batch_map(document)

    batches = document["batches"]
    assert isinstance(batches, list)
    assert len(batches) == 14
    assert sum(batch["batch_bytes"] for batch in batches) == 487_703_207
    assert len({batch["batch_id"] for batch in batches}) == 14
    assert len({batch["dvc_target"] for batch in batches}) == 14


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        (lambda value: value.update({"unexpected": True}), "unexpected root keys"),
        (
            lambda value: value["batches"][1].update({"batch_id": value["batches"][0]["batch_id"]}),
            "batch_id",
        ),
        (
            lambda value: value["batches"][1].update(
                {"dvc_target": value["batches"][0]["dvc_target"]}
            ),
            "dvc_target",
        ),
        (lambda value: value["batches"][0].update({"batch_bytes": -1}), "batch_bytes"),
        (lambda value: value["batches"][0].update({"evidence_ids": []}), "evidence_ids"),
        (
            lambda value: value["batches"][0].update(
                {"source_entries": [], "source_manifest": None}
            ),
            "exactly one source",
        ),
        (
            lambda value: value["totals"].update({"payload_bytes": 1}),
            "payload_bytes",
        ),
    ],
)
def test_batch_map_rejects_ambiguous_or_inconsistent_documents(
    mutation: object,
    match: str,
) -> None:
    document = copy.deepcopy(_load_batch_map())
    mutation(document)

    with pytest.raises(BatchMapError, match=match):
        validate_batch_map(document)


def test_batch_map_json_is_canonical() -> None:
    document = _load_batch_map()
    expected = (
        json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    )

    assert BATCH_MAP_PATH.read_text(encoding="utf-8") == expected


def test_batch_map_pins_its_committed_source_documents() -> None:
    document = _load_batch_map()

    for source in document["source_documents"]:
        source_path = REPOSITORY_ROOT / source["path"]
        assert hashlib.sha256(source_path.read_bytes()).hexdigest() == source["sha256"]


def test_batch_map_matches_audited_inventory_bytes_and_full_hashes() -> None:
    document = _load_batch_map()
    inventory = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    audited_assets = {asset["source_relative_path"]: asset for asset in inventory["assets"]}

    mapped_sources: set[str] = set()
    for batch in document["batches"]:
        if batch["source_entries"] is None:
            continue
        for source in batch["source_entries"]:
            path = source["source_relative_path"]
            assert path not in mapped_sources
            assert source["bytes"] == audited_assets[path]["bytes"]
            assert source["sha256"] == audited_assets[path]["sha256"]
            mapped_sources.add(path)

    assert "cap51_livedb/sfm_live.db-shm" not in mapped_sources
    assert document["exclusions"] == [
        {
            "evidence_id": "cap51-replay-shm-drift",
            "persistent_copy_eligible": False,
            "reason": (
                "SQLite SHM is a volatile WAL index with observed hash drift; retain only its "
                "recorded forensic hashes and never copy it as replay state."
            ),
            "source_relative_path": "cap51_livedb/sfm_live.db-shm",
        }
    ]


def test_manifest_batches_bind_exact_collection_counts_bytes_and_hashes() -> None:
    document = _load_batch_map()
    manifest_batches = [batch for batch in document["batches"] if batch["source_manifest"]]

    assert len(manifest_batches) == 2
    for batch in manifest_batches:
        reference = batch["source_manifest"]
        manifest_path = REPOSITORY_ROOT / reference["path"]
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        assert reference["sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
        assert reference["collection_id"] == manifest["collection_id"]
        assert reference["asset_count"] == len(manifest["assets"])
        assert reference["total_bytes"] == sum(asset["bytes"] for asset in manifest["assets"])
        assert batch["batch_bytes"] == reference["total_bytes"]


def test_batch_evidence_ids_are_bound_by_the_three_pinned_contracts() -> None:
    document = _load_batch_map()
    contract_paths = [
        REPOSITORY_ROOT / source["path"]
        for source in document["source_documents"]
        if source["document_id"].endswith("contract")
    ]

    def collect_evidence_ids(value: object) -> set[str]:
        if isinstance(value, dict):
            own = {value["evidence_id"]} if isinstance(value.get("evidence_id"), str) else set()
            return own | set().union(*(collect_evidence_ids(item) for item in value.values()))
        if isinstance(value, list):
            return set().union(*(collect_evidence_ids(item) for item in value))
        return set()

    contract_evidence_ids = set().union(
        *(
            collect_evidence_ids(json.loads(path.read_text(encoding="utf-8")))
            for path in contract_paths
        )
    )
    mapped_evidence_ids = {
        evidence_id for batch in document["batches"] for evidence_id in batch["evidence_ids"]
    }

    assert len(contract_paths) == 3
    assert mapped_evidence_ids <= contract_evidence_ids
    assert {item["evidence_id"] for item in document["exclusions"]} <= contract_evidence_ids


def test_batch_targets_and_sizes_are_the_reviewed_fourteen_unit_map() -> None:
    document = _load_batch_map()
    observed = {
        batch["batch_id"]: (batch["batch_bytes"], batch["dvc_target"])
        for batch in document["batches"]
    }

    assert observed == {
        "cap50-raw-selected-115": (
            205_162_291,
            "data/pocketworld_captures/cap50/raw/photos_highres",
        ),
        "cap50-work-png-115": (
            96_336_651,
            "data/pocketworld_captures/cap50/derived/work_1024x576",
        ),
        "cap50-live-feed-ledger": (
            84_167,
            "data/pocketworld_captures/cap50/private_manifests/sfm_fed_frames.jsonl",
        ),
        "cap50-subset-meta": (
            68_706,
            "data/pocketworld_captures/cap50/private_manifests/subset_meta_cap50full.json",
        ),
        "cap50-ghost-mask": (
            374,
            "data/pocketworld_captures/cap50/private_manifests/ghost_mask.json",
        ),
        "cap50-sparse-ply": (1_392_980, "data/pocketworld_captures/cap50/sfm/sfm_sparse.ply"),
        "cap51-shared-feed-ledger": (
            63_442,
            "data/pocketworld_captures/cap51/private_manifests/sfm_fed_frames.jsonl",
        ),
        "cap51-photo-bundle": (
            164_416,
            "data/pocketworld_captures/cap51/private_manifests/photo_bundle.json",
        ),
        "cap51-sparse-ply": (966_125, "data/pocketworld_captures/cap51/sfm/sfm_sparse.ply"),
        "cap51-replay-db-and-wal": (
            134_979_640,
            "data/pocketworld_captures/cap51/replay_database",
        ),
        "cap50-requested-four-ply": (
            1_729_833,
            "experiments/floor_plane_sweep_densifier_2026-07-13/contract/outputs",
        ),
        "cap50-merge-input-two-ply": (
            341_823,
            "experiments/floor_plane_sweep_densifier_2026-07-13/contract/intermediates/merge_inputs",
        ),
        "cap50-noncommercial-matcher-five-npz": (
            42_763_616,
            "experiments/floor_plane_sweep_densifier_2026-07-13/contract/intermediates/"
            "noncommercial_matches",
        ),
        "cap50-diagnostic-two-npz": (
            3_649_143,
            "experiments/floor_plane_sweep_densifier_2026-07-13/contract/intermediates/diagnostics",
        ),
    }


def test_cap51_feed_ledger_is_preserved_once_for_both_contract_evidence_ids() -> None:
    document = _load_batch_map()
    matching = [
        batch
        for batch in document["batches"]
        if any(
            source["source_relative_path"] == "cap51_diag/sfm_fed_frames.jsonl"
            for source in batch["source_entries"] or []
        )
    ]

    assert len(matching) == 1
    assert matching[0]["evidence_ids"] == ["cap51-feed-ledger", "cap51-replay-pose-ledger"]


def test_parse_resource_snapshot_extracts_disk_bytes_and_memory_percentage() -> None:
    df_output = (
        "Filesystem 1024-blocks Used Available Capacity iused ifree %iused Mounted on\n"
        "/dev/disk3s5 100000000 50000000 20000000 72% 1 2 0% /System/Volumes/Data\n"
    )
    memory_output = (
        "The system has 19327352832 (1179648 pages with a page size of 16384).\n"
        "System-wide memory free percentage: 37%\n"
    )

    snapshot = parse_resource_snapshot(df_output, memory_output)

    assert snapshot == ResourceSnapshot(
        free_disk_bytes=20_000_000 * 1024,
        memory_available_percent=37.0,
    )


@pytest.mark.parametrize(
    ("df_output", "memory_output"),
    [
        ("", "System-wide memory free percentage: 37%\n"),
        ("header only\n", "System-wide memory free percentage: 37%\n"),
        (
            "Filesystem 1024-blocks Used Available\n/dev/disk 1 2 nope\n",
            "System-wide memory free percentage: 37%\n",
        ),
        (
            "Filesystem 1024-blocks Used Available\n/dev/disk 1 2 3\n",
            "memory pressure unavailable\n",
        ),
        (
            "Filesystem 1024-blocks Used Available\n/dev/disk 1 2 3\n",
            "System-wide memory free percentage: 37%\nSystem-wide memory free percentage: 38%\n",
        ),
    ],
)
def test_parse_resource_snapshot_fails_closed_on_ambiguous_output(
    df_output: str,
    memory_output: str,
) -> None:
    with pytest.raises(ResourceSnapshotError):
        parse_resource_snapshot(df_output, memory_output)


def test_resource_gate_requires_disk_formula_and_at_least_twenty_percent_memory() -> None:
    batch_bytes = 1_000
    required = required_disk_bytes(batch_bytes)

    passing = evaluate_resource_gate(
        ResourceSnapshot(free_disk_bytes=required, memory_available_percent=20.0),
        batch_bytes,
    )
    disk_failure = evaluate_resource_gate(
        ResourceSnapshot(free_disk_bytes=required - 1, memory_available_percent=100.0),
        batch_bytes,
    )
    memory_failure = evaluate_resource_gate(
        ResourceSnapshot(free_disk_bytes=required, memory_available_percent=19.99),
        batch_bytes,
    )

    assert passing.allowed is True
    assert passing.required_disk_bytes == required
    assert disk_failure.allowed is False
    assert disk_failure.disk_ok is False
    assert memory_failure.allowed is False
    assert memory_failure.memory_ok is False


@pytest.mark.parametrize(
    "snapshot",
    [
        ResourceSnapshot(free_disk_bytes=-1, memory_available_percent=50.0),
        ResourceSnapshot(free_disk_bytes=1, memory_available_percent=-0.1),
        ResourceSnapshot(free_disk_bytes=1, memory_available_percent=100.1),
    ],
)
def test_resource_gate_rejects_invalid_snapshots(snapshot: ResourceSnapshot) -> None:
    with pytest.raises(ResourceSnapshotError):
        evaluate_resource_gate(snapshot, 1)


@pytest.mark.parametrize(
    "path",
    [
        "capture.jpg",
        "capture.JPEG",
        "derived.png",
        "fixture.db",
        "fixture.sqlite",
        "fixture.sqlite3",
        "fixture.db-wal",
        "fixture.db-shm",
        "cloud.ply",
        "matches.npz",
        "array.npy",
        "experiments/output.PLY",
    ],
)
def test_git_path_classifier_rejects_payload_suffixes_everywhere(path: str) -> None:
    violations = find_forbidden_git_paths([path])

    assert len(violations) == 1
    assert violations[0].path == path
    assert violations[0].reason == "payload_suffix"


@pytest.mark.parametrize(
    "path",
    [
        "data/pocketworld_captures/cap50/README.md",
        "data/pocketworld_captures/cap50/manifest.json",
        "data/pocketworld_captures/.dvc/config",
    ],
)
def test_git_path_classifier_rejects_non_dvc_metadata_inside_capture_root(path: str) -> None:
    violations = find_forbidden_git_paths([path])

    assert [(item.path, item.reason) for item in violations] == [
        (path, "capture_root_metadata_only")
    ]


@pytest.mark.parametrize(
    "path",
    [
        "data/pocketworld_captures/cap50/raw_selected_115.dvc",
        "data/pocketworld_captures/cap50/.gitignore",
        "docs/research-contract.md",
        "data/pocketworld_captures-other/README.md",
    ],
)
def test_git_path_classifier_allows_only_explicit_capture_metadata(path: str) -> None:
    assert find_forbidden_git_paths([path]) == ()


@pytest.mark.parametrize("path", ["", "../escape", "/absolute", "a/./b", "a\\b", "a\nb"])
def test_git_path_classifier_fails_closed_on_ambiguous_paths(path: str) -> None:
    violations = find_forbidden_git_paths([path])

    assert len(violations) == 1
    assert violations[0].reason == "invalid_path"


def test_git_path_classifier_preserves_input_order_for_staged_or_history_paths() -> None:
    paths = ["safe.txt", "first.npy", "data/pocketworld_captures/cap50/unsafe.txt"]

    violations = find_forbidden_git_paths(paths)

    assert [item.path for item in violations] == paths[1:]


def test_clonefile_regular_uses_nofollow_flags_and_verifies_size_and_sha(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"small immutable fixture")
    calls: list[tuple[bytes, bytes, int]] = []

    def fake_clone(source_bytes: bytes, destination_bytes: bytes, flags: int) -> int:
        calls.append((source_bytes, destination_bytes, flags))
        Path(os.fsdecode(destination_bytes)).write_bytes(
            Path(os.fsdecode(source_bytes)).read_bytes()
        )
        return 0

    result = clonefile_regular(source, destination, clonefile_fn=fake_clone)

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert calls == [(os.fsencode(source), os.fsencode(destination), 0xA)]
    assert CLONE_FLAGS == 0xA
    assert result == CloneVerification(bytes=len(source.read_bytes()), sha256=digest)
    assert destination.read_bytes() == source.read_bytes()


def test_clonefile_regular_rejects_preexisting_destination_without_touching_it(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"source")
    destination.write_bytes(b"keep me")
    called = False

    def must_not_run(_source: bytes, _destination: bytes, _flags: int) -> int:
        nonlocal called
        called = True
        return 0

    with pytest.raises(CloneFileError, match="destination must not exist"):
        clonefile_regular(source, destination, clonefile_fn=must_not_run)

    assert called is False
    assert destination.read_bytes() == b"keep me"


@pytest.mark.parametrize("source_kind", ["directory", "symlink", "symlink_parent"])
def test_clonefile_regular_rejects_nonregular_or_symlinked_sources(
    tmp_path: Path,
    source_kind: str,
) -> None:
    real = tmp_path / "real.bin"
    real.write_bytes(b"source")
    if source_kind == "directory":
        source = tmp_path / "source-directory"
        source.mkdir()
    elif source_kind == "symlink":
        source = tmp_path / "source-link"
        source.symlink_to(real)
    else:
        real_parent = tmp_path / "real-parent"
        real_parent.mkdir()
        source = real_parent / "source.bin"
        source.write_bytes(b"source")
        linked_parent = tmp_path / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        source = linked_parent / "source.bin"
    destination = tmp_path / "destination.bin"

    with pytest.raises(CloneFileError):
        clonefile_regular(source, destination, clonefile_fn=lambda *_args: 0)

    assert not destination.exists()


def test_clonefile_regular_removes_partial_new_destination_when_clone_fails(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"source")

    def failing_clone(_source: bytes, destination_bytes: bytes, _flags: int) -> int:
        Path(os.fsdecode(destination_bytes)).write_bytes(b"partial")
        return -1

    with pytest.raises(CloneFileError, match="clonefile failed"):
        clonefile_regular(source, destination, clonefile_fn=failing_clone)

    assert not destination.exists()


def test_clonefile_regular_removes_new_destination_on_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"source")

    def corrupt_clone(_source: bytes, destination_bytes: bytes, _flags: int) -> int:
        Path(os.fsdecode(destination_bytes)).write_bytes(b"corrupt")
        return 0

    with pytest.raises(CloneFileError, match="size or SHA-256 mismatch"):
        clonefile_regular(source, destination, clonefile_fn=corrupt_clone)

    assert not destination.exists()


def test_clonefile_regular_detects_source_mutation_and_cleans_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"source")

    def mutating_clone(source_bytes: bytes, destination_bytes: bytes, _flags: int) -> int:
        source_path = Path(os.fsdecode(source_bytes))
        Path(os.fsdecode(destination_bytes)).write_bytes(source_path.read_bytes())
        source_path.write_bytes(b"changed")
        return 0

    with pytest.raises(CloneFileError, match="source changed"):
        clonefile_regular(source, destination, clonefile_fn=mutating_clone)

    assert not destination.exists()


@pytest.mark.skipif(sys.platform != "darwin", reason="clonefile is a macOS primitive")
def test_clonefile_regular_tiny_real_apfs_smoke(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination.bin"
    source.write_bytes(b"tiny APFS clone smoke")

    verification = clonefile_regular(source, destination)

    assert verification.bytes < 1024
    assert destination.read_bytes() == source.read_bytes()


@pytest.mark.parametrize(
    "path",
    [
        "data/pocketworld_captures/cap50/derived/work_1024x576/frame.png",
        "data/pocketworld_captures/cap50/private_manifests/subset_meta.json",
        "data/pocketworld_captures/cap50/private_manifests/feed.jsonl",
        "data/pocketworld_captures/cap51/replay_database/sfm_live.db-wal",
        "data/pocketworld_captures/cap51/replay_database/sfm_live.db-shm",
    ],
)
def test_capture_payload_gitignore_covers_new_explicit_patterns(path: str) -> None:
    assert _git_check_ignored(path)


@pytest.mark.parametrize(
    "path",
    [
        "data/pocketworld_captures/cap50/raw/photos_highres/frame.jpg",
        "data/pocketworld_captures/cap51/replay_database/sfm_live.db",
        "data/pocketworld_captures/cap50/sfm/sfm_sparse.ply",
        "data/pocketworld_captures/cap50/research/matches.npz",
    ],
)
def test_capture_payload_gitignore_retains_existing_payload_patterns(path: str) -> None:
    assert _git_check_ignored(path)


def test_capture_dvc_pointer_is_not_ignored() -> None:
    assert not _git_check_ignored("data/pocketworld_captures/cap50/raw/photos_highres.dvc")
