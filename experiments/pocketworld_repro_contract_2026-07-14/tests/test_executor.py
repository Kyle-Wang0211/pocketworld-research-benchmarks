from __future__ import annotations

import hashlib
import os
from typing import TYPE_CHECKING

import pytest

from pocketworld_contract import executor
from pocketworld_contract.executor import ExecutionError, ExecutionSummary, execute_batch
from pocketworld_contract.manifest import canonical_json
from pocketworld_contract.preservation import CloneFileError, CloneVerification

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source_entry(source_relative_path: str, payload: bytes) -> dict[str, object]:
    return {
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "source_relative_path": source_relative_path,
    }


def _entry_batch(
    entries: list[dict[str, object]],
    *,
    dvc_target: str = "data/preserved",
) -> dict[str, object]:
    return {
        "batch_bytes": sum(int(entry["bytes"]) for entry in entries),
        "batch_id": "synthetic-entry-batch",
        "dvc_target": dvc_target,
        "evidence_ids": ["synthetic-evidence"],
        "source_entries": entries,
        "source_manifest": None,
    }


def _manifest_asset(path: str, payload: bytes) -> dict[str, object]:
    return {
        "bytes": len(payload),
        "evidence_role": "synthetic-test-input",
        "license_status": "synthetic-test-owned",
        "lineage_contains_noncommercial": False,
        "path": path,
        "platform_qualification": "synthetic-test-only",
        "role": "metadata",
        "sha256": _sha256(payload),
    }


def _manifest_batch(
    repository_root: Path,
    assets: list[dict[str, object]],
) -> dict[str, object]:
    manifest = {
        "assets": assets,
        "collection_id": "synthetic-collection-v1",
        "schema_version": 1,
    }
    manifest_bytes = canonical_json(manifest).encode()
    manifest_path = repository_root / "manifests" / "source-v1.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(manifest_bytes)
    total_bytes = sum(int(asset["bytes"]) for asset in assets)
    return {
        "batch_bytes": total_bytes,
        "batch_id": "synthetic-manifest-batch",
        "dvc_target": "data/collection",
        "evidence_ids": ["synthetic-manifest"],
        "source_entries": None,
        "source_manifest": {
            "asset_count": len(assets),
            "collection_id": "synthetic-collection-v1",
            "path": "manifests/source-v1.json",
            "sha256": _sha256(manifest_bytes),
            "total_bytes": total_bytes,
        },
    }


def _link_clone(
    events: list[tuple[str, object]],
) -> Callable[[Path, Path], CloneVerification]:
    def clone(source: Path, destination: Path) -> CloneVerification:
        events.append(("clone", source.name))
        os.link(source, destination)
        payload = source.read_bytes()
        return CloneVerification(bytes=len(payload), sha256=_sha256(payload))

    return clone


def test_source_entries_execute_serially_in_deterministic_path_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "source"
    repository_root.mkdir()
    source_root.mkdir()
    payloads = {"b.bin": b"second", "a.bin": b"first"}
    for name, payload in payloads.items():
        (source_root / name).write_bytes(payload)
    batch = _entry_batch(
        [
            _source_entry("scratch/b.bin", payloads["b.bin"]),
            _source_entry("scratch/a.bin", payloads["a.bin"]),
        ]
    )
    events: list[tuple[str, object]] = []
    monkeypatch.setattr(executor, "clonefile_regular", _link_clone(events))

    def resource_check(batch_bytes: int) -> None:
        events.append(("resource", batch_bytes))

    result = execute_batch(
        batch,
        repository_root=repository_root,
        source_roots={"scratch": source_root},
        resource_check=resource_check,
    )

    assert result == ExecutionSummary(
        batch_id="synthetic-entry-batch",
        total_files=2,
        cloned_files=2,
        resumed_files=0,
        verified_bytes=11,
        cleanup_warning_count=0,
    )
    assert events == [
        ("resource", 11),
        ("clone", "a.bin"),
        ("clone", "b.bin"),
    ]
    assert (repository_root / "data/preserved/a.bin").read_bytes() == b"first"
    assert (repository_root / "data/preserved/b.bin").read_bytes() == b"second"


def test_manifest_assets_use_collection_root_and_manifest_relative_destinations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "collection-source"
    repository_root.mkdir()
    source_root.mkdir()
    (source_root / "a.json").write_bytes(b"a")
    (source_root / "nested").mkdir()
    (source_root / "nested/b.json").write_bytes(b"bb")
    assets = [
        _manifest_asset("a.json", b"a"),
        _manifest_asset("nested/b.json", b"bb"),
    ]
    batch = _manifest_batch(repository_root, assets)
    events: list[tuple[str, object]] = []
    monkeypatch.setattr(executor, "clonefile_regular", _link_clone(events))

    result = execute_batch(
        batch,
        repository_root=repository_root,
        source_roots={"synthetic-collection-v1": source_root},
        resource_check=lambda file_bytes: events.append(("resource", file_bytes)),
    )

    assert result.total_files == 2
    assert result.cloned_files == 2
    assert result.verified_bytes == 3
    assert events == [
        ("resource", 3),
        ("clone", "a.json"),
        ("clone", "b.json"),
    ]
    assert (repository_root / "data/collection/a.json").read_bytes() == b"a"
    assert (repository_root / "data/collection/nested/b.json").read_bytes() == b"bb"


def test_exact_regular_destination_resumes_without_cloning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "source"
    destination = repository_root / "data/exact.bin"
    repository_root.mkdir()
    source_root.mkdir()
    (source_root / "exact.bin").write_bytes(b"already safe")
    destination.parent.mkdir()
    destination.write_bytes(b"already safe")
    batch = _entry_batch(
        [_source_entry("scratch/exact.bin", b"already safe")],
        dvc_target="data/exact.bin",
    )
    resources: list[int] = []

    def unexpected_clone(_source: Path, _destination: Path) -> CloneVerification:
        pytest.fail("an exact destination must resume without clonefile")

    monkeypatch.setattr(executor, "clonefile_regular", unexpected_clone)

    result = execute_batch(
        batch,
        repository_root=repository_root,
        source_roots={"scratch": source_root},
        resource_check=resources.append,
    )

    assert result.resumed_files == 1
    assert result.cloned_files == 0
    assert resources == [12]
    assert destination.read_bytes() == b"already safe"


def test_mismatched_existing_destination_is_preserved_and_stops(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "source"
    destination = repository_root / "data/exact.bin"
    repository_root.mkdir()
    source_root.mkdir()
    (source_root / "exact.bin").write_bytes(b"expected")
    destination.parent.mkdir()
    destination.write_bytes(b"foreign")
    batch = _entry_batch(
        [_source_entry("scratch/exact.bin", b"expected")],
        dvc_target="data/exact.bin",
    )

    def unexpected_clone(_source: Path, _destination: Path) -> CloneVerification:
        pytest.fail("a foreign destination must never be overwritten")

    monkeypatch.setattr(executor, "clonefile_regular", unexpected_clone)

    with pytest.raises(ExecutionError, match="existing destination does not match"):
        execute_batch(
            batch,
            repository_root=repository_root,
            source_roots={"scratch": source_root},
            resource_check=lambda _file_bytes: None,
        )

    assert destination.read_bytes() == b"foreign"


def test_source_hash_mismatch_stops_before_destination_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "source"
    repository_root.mkdir()
    source_root.mkdir()
    (source_root / "asset.bin").write_bytes(b"mutated")
    batch = _entry_batch(
        [_source_entry("scratch/asset.bin", b"expected")],
        dvc_target="data/asset.bin",
    )

    def unexpected_clone(_source: Path, _destination: Path) -> CloneVerification:
        pytest.fail("a mismatched source must not be cloned")

    monkeypatch.setattr(executor, "clonefile_regular", unexpected_clone)

    with pytest.raises(ExecutionError, match="source does not match"):
        execute_batch(
            batch,
            repository_root=repository_root,
            source_roots={"scratch": source_root},
            resource_check=lambda _file_bytes: None,
        )

    assert not (repository_root / "data").exists()


def test_source_symlink_component_is_rejected_without_following_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "source"
    outside = tmp_path / "outside"
    repository_root.mkdir()
    source_root.mkdir()
    outside.mkdir()
    (outside / "asset.bin").write_bytes(b"private")
    (source_root / "linked").symlink_to(outside, target_is_directory=True)
    batch = _entry_batch(
        [_source_entry("scratch/linked/asset.bin", b"private")],
        dvc_target="data/asset.bin",
    )

    def unexpected_clone(_source: Path, _destination: Path) -> CloneVerification:
        pytest.fail("source symlinks must not be followed")

    monkeypatch.setattr(executor, "clonefile_regular", unexpected_clone)

    with pytest.raises(ExecutionError, match=r"source.*symlink|source.*safely"):
        execute_batch(
            batch,
            repository_root=repository_root,
            source_roots={"scratch": source_root},
            resource_check=lambda _file_bytes: None,
        )

    assert not (repository_root / "data").exists()


def test_destination_parent_symlink_is_rejected_without_external_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "source"
    outside = tmp_path / "outside"
    repository_root.mkdir()
    source_root.mkdir()
    outside.mkdir()
    (source_root / "asset.bin").write_bytes(b"expected")
    (repository_root / "data").symlink_to(outside, target_is_directory=True)
    batch = _entry_batch(
        [_source_entry("scratch/asset.bin", b"expected")],
        dvc_target="data/asset.bin",
    )

    def unexpected_clone(_source: Path, _destination: Path) -> CloneVerification:
        pytest.fail("unsafe destination parents must stop before clonefile")

    monkeypatch.setattr(executor, "clonefile_regular", unexpected_clone)

    with pytest.raises(ExecutionError, match=r"destination.*symlink|destination.*safely"):
        execute_batch(
            batch,
            repository_root=repository_root,
            source_roots={"scratch": source_root},
            resource_check=lambda _file_bytes: None,
        )

    assert not (outside / "asset.bin").exists()


def test_denied_resource_callback_stops_before_source_or_destination_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    batch = _entry_batch(
        [_source_entry("scratch/missing.bin", b"expected")],
        dvc_target="data/asset.bin",
    )

    def unexpected_clone(_source: Path, _destination: Path) -> CloneVerification:
        pytest.fail("resource denial must stop before clonefile")

    monkeypatch.setattr(executor, "clonefile_regular", unexpected_clone)

    with pytest.raises(ExecutionError, match="resource check denied"):
        execute_batch(
            batch,
            repository_root=repository_root,
            source_roots={"scratch": tmp_path / "missing-source-root"},
            resource_check=lambda _file_bytes: False,
        )

    assert not (repository_root / "data").exists()


def test_batch_resource_gate_receives_total_before_any_file_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    batch = _entry_batch(
        [
            _source_entry("scratch/a.bin", b"first"),
            _source_entry("scratch/b.bin", b"second"),
        ]
    )
    resource_calls: list[int] = []

    def unexpected_clone(_source: Path, _destination: Path) -> CloneVerification:
        pytest.fail("a denied batch must clone zero files")

    def deny_batch(batch_bytes: int) -> bool:
        resource_calls.append(batch_bytes)
        return False

    monkeypatch.setattr(executor, "clonefile_regular", unexpected_clone)

    with pytest.raises(ExecutionError, match="resource check denied"):
        execute_batch(
            batch,
            repository_root=repository_root,
            source_roots={"scratch": tmp_path / "missing-source-root"},
            resource_check=deny_batch,
        )

    assert resource_calls == [11]
    assert not (repository_root / "data").exists()


def test_clone_failure_stops_serial_execution_before_the_next_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "source"
    repository_root.mkdir()
    source_root.mkdir()
    payloads = {name: name.encode() for name in ("a.bin", "b.bin", "c.bin")}
    for name, payload in payloads.items():
        (source_root / name).write_bytes(payload)
    batch = _entry_batch(
        [_source_entry(f"scratch/{name}", payload) for name, payload in payloads.items()]
    )
    events: list[tuple[str, object]] = []

    def fail_second(source: Path, destination: Path) -> CloneVerification:
        events.append(("clone", source.name))
        if source.name == "b.bin":
            raise CloneFileError("synthetic clone failure")
        os.link(source, destination)
        payload = source.read_bytes()
        return CloneVerification(bytes=len(payload), sha256=_sha256(payload))

    monkeypatch.setattr(executor, "clonefile_regular", fail_second)

    with pytest.raises(CloneFileError, match="synthetic clone failure"):
        execute_batch(
            batch,
            repository_root=repository_root,
            source_roots={"scratch": source_root},
            resource_check=lambda file_bytes: events.append(("resource", file_bytes)),
        )

    assert events == [
        ("resource", 15),
        ("clone", "a.bin"),
        ("clone", "b.bin"),
    ]
    assert (repository_root / "data/preserved/a.bin").exists()
    assert not (repository_root / "data/preserved/c.bin").exists()


def test_manifest_reference_hash_mismatch_stops_before_resource_callback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository_root = tmp_path / "repository"
    source_root = tmp_path / "source"
    repository_root.mkdir()
    source_root.mkdir()
    (source_root / "a.json").write_bytes(b"a")
    batch = _manifest_batch(repository_root, [_manifest_asset("a.json", b"a")])
    manifest_path = repository_root / "manifests/source-v1.json"
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")
    resource_calls: list[int] = []

    def unexpected_clone(_source: Path, _destination: Path) -> CloneVerification:
        pytest.fail("an unpinned manifest must not drive preservation")

    monkeypatch.setattr(executor, "clonefile_regular", unexpected_clone)

    with pytest.raises(ExecutionError, match="source manifest does not match"):
        execute_batch(
            batch,
            repository_root=repository_root,
            source_roots={"synthetic-collection-v1": source_root},
            resource_check=resource_calls.append,
        )

    assert resource_calls == [1]
    assert not (repository_root / "data").exists()
