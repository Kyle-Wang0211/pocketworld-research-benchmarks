from __future__ import annotations

import hashlib
import importlib
import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType


def _manifest_module() -> ModuleType:
    return importlib.import_module("pocketworld_contract.manifest")


def _sample_collection(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    manifest = _manifest_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "capture.jpg").write_bytes(b"jpeg fixture")
    collection = manifest.build_collection(
        root,
        "fixture",
        license_status="license-reviewed",
        platform_qualification="local-only",
        evidence_role="diagnostic",
        lineage_contains_noncommercial=False,
    )
    return root, collection


def test_canonical_json_is_sorted_compact_utf8_and_newline_terminated() -> None:
    manifest = _manifest_module()

    rendered = manifest.canonical_json({"z": "雪", "a": {"y": 2, "x": 1}})

    assert rendered == '{"a":{"x":1,"y":2},"z":"雪"}\n'


def test_sha256_file_hashes_content_larger_than_one_streaming_chunk(tmp_path: Path) -> None:
    manifest = _manifest_module()
    payload = (b"0123456789abcdef" * (4 * 1024 * 1024 // 16)) + b"tail"
    asset = tmp_path / "large.bin"
    asset.write_bytes(payload)

    assert manifest.sha256_file(asset) == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    "unsafe_path",
    ["", ".", "..", "/absolute", "a/../b", "a/./b", "a//b", "a\\b", "C:/asset"],
)
def test_safe_relative_path_rejects_ambiguous_or_traversing_paths(unsafe_path: str) -> None:
    manifest = _manifest_module()

    with pytest.raises(manifest.ContractError):
        manifest.safe_relative_path(unsafe_path)


def test_safe_relative_path_preserves_normalized_posix_path() -> None:
    manifest = _manifest_module()

    assert manifest.safe_relative_path("nested/asset.bin") == "nested/asset.bin"


def test_build_collection_is_deterministic_and_maps_roles(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root = tmp_path / "assets"
    nested = root / "nested"
    nested.mkdir(parents=True)
    fixtures = {
        "capture.JPG": (b"jpg", "capture_image"),
        "capture.jpeg": (b"jpeg", "capture_image"),
        "derived.png": (b"png", "derived_image"),
        "events.jsonl": (b"{}\n", "event_log"),
        "metadata.json": (b"{}", "metadata"),
        "nested/archive.npz": (b"npz", "numpy_archive"),
        "nested/cloud.ply": (b"ply", "point_cloud"),
        "notes.bin": (b"notes", "asset"),
        "state.db": (b"db", "sqlite_database"),
        "state.db-shm": (b"shm", "sqlite_shm"),
        "state.db-wal": (b"wal", "sqlite_wal"),
    }
    for relative_path, (payload, _role) in fixtures.items():
        asset = root / relative_path
        asset.parent.mkdir(parents=True, exist_ok=True)
        asset.write_bytes(payload)

    axes = {
        "license_status": "custom-license-label",
        "platform_qualification": "custom-platform-label",
        "evidence_role": "custom-evidence-label",
        "lineage_contains_noncommercial": True,
    }
    first = manifest.build_collection(root, "local-fixture", **axes)
    second = manifest.build_collection(root, "local-fixture", **axes)

    assets = first["assets"]
    assert [asset["path"] for asset in assets] == sorted(fixtures)
    assert first == second
    assert manifest.canonical_json(first) == manifest.canonical_json(second)
    assert set(first) == {"schema_version", "collection_id", "assets"}
    assert first["schema_version"] == 1
    assert first["collection_id"] == "local-fixture"
    for asset in assets:
        payload = fixtures[asset["path"]][0]
        assert set(asset) == {
            "path",
            "role",
            "bytes",
            "sha256",
            "license_status",
            "platform_qualification",
            "evidence_role",
            "lineage_contains_noncommercial",
        }
        assert asset["role"] == fixtures[asset["path"]][1]
        assert asset["bytes"] == len(payload)
        assert asset["sha256"] == hashlib.sha256(payload).hexdigest()
        assert {axis: asset[axis] for axis in axes} == axes


def test_verify_collection_accepts_an_exact_unchanged_collection(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root, collection = _sample_collection(tmp_path)

    manifest.verify_collection(root, collection)


def test_verify_collection_rejects_boolean_schema_version(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root, collection = _sample_collection(tmp_path)
    collection["schema_version"] = True

    with pytest.raises(manifest.ContractError, match="schema_version"):
        manifest.verify_collection(root, collection)


@pytest.mark.parametrize("extra_location", ["manifest", "asset"])
def test_verify_collection_rejects_unknown_manifest_fields(
    tmp_path: Path,
    extra_location: str,
) -> None:
    manifest = _manifest_module()
    root, collection = _sample_collection(tmp_path)
    if extra_location == "manifest":
        collection["future_metadata"] = "not-in-schema"
    else:
        collection["assets"][0]["commercial_eligibility"] = "obsolete-axis"

    with pytest.raises(manifest.ContractError, match="exactly"):
        manifest.verify_collection(root, collection)


def test_verify_collection_rejects_same_size_mutation(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root, collection = _sample_collection(tmp_path)
    (root / "capture.jpg").write_bytes(b"JPEG FIXTURE")

    with pytest.raises(manifest.ContractError, match="mutated"):
        manifest.verify_collection(root, collection)


def test_verify_collection_rejects_missing_file(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root, collection = _sample_collection(tmp_path)
    (root / "capture.jpg").unlink()

    with pytest.raises(manifest.ContractError, match="missing"):
        manifest.verify_collection(root, collection)


def test_verify_collection_rejects_extra_file(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root, collection = _sample_collection(tmp_path)
    (root / "extra.bin").write_bytes(b"extra")

    with pytest.raises(manifest.ContractError, match="extra"):
        manifest.verify_collection(root, collection)


def test_verify_collection_rejects_duplicate_manifest_path(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root, collection = _sample_collection(tmp_path)
    assets = collection["assets"]
    assets.append(dict(assets[0]))

    with pytest.raises(manifest.ContractError, match="duplicate"):
        manifest.verify_collection(root, collection)


def test_verify_collection_rejects_noncanonical_asset_order(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "a.bin").write_bytes(b"a")
    (root / "b.bin").write_bytes(b"b")
    collection = manifest.build_collection(
        root,
        "fixture",
        license_status="license-reviewed",
        platform_qualification="local-only",
        evidence_role="diagnostic",
        lineage_contains_noncommercial=False,
    )
    collection["assets"].reverse()

    with pytest.raises(manifest.ContractError, match=r"canonical|sorted"):
        manifest.verify_collection(root, collection)


def test_verify_collection_rejects_unsafe_manifest_path(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root, collection = _sample_collection(tmp_path)
    collection["assets"][0]["path"] = "../capture.jpg"

    with pytest.raises(manifest.ContractError):
        manifest.verify_collection(root, collection)


def test_build_and_verify_reject_symlinks_anywhere(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root, collection = _sample_collection(tmp_path)
    link = root / "linked.jpg"
    link.symlink_to(root / "capture.jpg")

    with pytest.raises(manifest.ContractError, match="symlink"):
        manifest.build_collection(
            root,
            "fixture",
            license_status="license-reviewed",
            platform_qualification="local-only",
            evidence_role="diagnostic",
            lineage_contains_noncommercial=False,
        )
    with pytest.raises(manifest.ContractError, match="symlink"):
        manifest.verify_collection(root, collection)


def test_build_collection_rejects_directory_scan_errors(tmp_path: Path) -> None:
    manifest = _manifest_module()
    root = tmp_path / "assets"
    restricted = root / "restricted"
    restricted.mkdir(parents=True)
    (restricted / "hidden.bin").write_bytes(b"must not be omitted")
    restricted.chmod(0)

    try:
        with pytest.raises(manifest.ContractError, match="scan"):
            manifest.build_collection(
                root,
                "fixture",
                license_status="license-reviewed",
                platform_qualification="local-only",
                evidence_role="diagnostic",
                lineage_contains_noncommercial=False,
            )
    finally:
        restricted.chmod(0o700)


def test_verify_rejects_file_replaced_by_symlink_after_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    root = tmp_path / "assets"
    root.mkdir()
    asset = root / "asset.bin"
    outside = tmp_path / "outside.bin"
    payload = b"x" * len(os.fsencode(outside))
    asset.write_bytes(payload)
    outside.write_bytes(payload)
    collection = manifest.build_collection(
        root,
        "fixture",
        license_status="license-reviewed",
        platform_qualification="local-only",
        evidence_role="diagnostic",
        lineage_contains_noncommercial=False,
    )
    original_scan = manifest._scan_regular_files  # noqa: SLF001 - deterministic race injection.

    def scan_then_swap(root_path: Path) -> object:
        scanned = original_scan(root_path)
        asset.unlink()
        asset.symlink_to(outside)
        return scanned

    monkeypatch.setattr(manifest, "_scan_regular_files", scan_then_swap)

    with pytest.raises(manifest.ContractError, match=r"changed|symlink|safely"):
        manifest.verify_collection(root, collection)


def test_verify_rejects_parent_directory_replaced_by_symlink_after_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    root = tmp_path / "assets"
    nested = root / "nested"
    nested.mkdir(parents=True)
    payload = b"same-content"
    (nested / "asset.bin").write_bytes(payload)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "asset.bin").write_bytes(payload)
    collection = manifest.build_collection(
        root,
        "fixture",
        license_status="license-reviewed",
        platform_qualification="local-only",
        evidence_role="diagnostic",
        lineage_contains_noncommercial=False,
    )
    original_scan = manifest._scan_regular_files  # noqa: SLF001 - deterministic race injection.

    def scan_then_swap(root_path: Path) -> object:
        scanned = original_scan(root_path)
        nested.rename(tmp_path / "original-nested")
        nested.symlink_to(outside, target_is_directory=True)
        return scanned

    monkeypatch.setattr(manifest, "_scan_regular_files", scan_then_swap)

    with pytest.raises(manifest.ContractError, match=r"changed|symlink|safely"):
        manifest.verify_collection(root, collection)


def test_verify_rejects_nested_file_added_after_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    root = tmp_path / "assets"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (nested / "asset.bin").write_bytes(b"fixture")
    collection = manifest.build_collection(
        root,
        "fixture",
        license_status="license-reviewed",
        platform_qualification="local-only",
        evidence_role="diagnostic",
        lineage_contains_noncommercial=False,
    )
    original_scan = manifest._scan_regular_files  # noqa: SLF001 - deterministic race injection.

    def scan_then_add(root_path: Path) -> object:
        scanned = original_scan(root_path)
        (nested / "extra.bin").write_bytes(b"late addition")
        return scanned

    monkeypatch.setattr(manifest, "_scan_regular_files", scan_then_add)

    with pytest.raises(manifest.ContractError, match=r"changed|extra|scan"):
        manifest.verify_collection(root, collection)


def test_build_rejects_earlier_file_mutated_while_later_file_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "a.bin").write_bytes(b"aaaa")
    earlier = root / "b.bin"
    earlier.write_bytes(b"bbbb")
    (root / "c.bin").write_bytes(b"cccc")
    original_hash = manifest._hash_descriptor  # noqa: SLF001 - deterministic race injection.
    hash_calls = 0

    def hash_then_mutate(descriptor: int) -> str:
        nonlocal hash_calls
        hash_calls += 1
        digest = original_hash(descriptor)
        if hash_calls == 3:
            earlier.write_bytes(b"zzzz")
        return digest

    monkeypatch.setattr(manifest, "_hash_descriptor", hash_then_mutate)

    with pytest.raises(manifest.ContractError, match="changed"):
        manifest.build_collection(
            root,
            "fixture",
            license_status="license-reviewed",
            platform_qualification="local-only",
            evidence_role="diagnostic",
            lineage_contains_noncommercial=False,
        )


def test_verify_rejects_earlier_file_mutated_while_later_file_hashes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "a.bin").write_bytes(b"aaaa")
    earlier = root / "b.bin"
    earlier.write_bytes(b"bbbb")
    (root / "c.bin").write_bytes(b"cccc")
    collection = manifest.build_collection(
        root,
        "fixture",
        license_status="license-reviewed",
        platform_qualification="local-only",
        evidence_role="diagnostic",
        lineage_contains_noncommercial=False,
    )
    original_hash = manifest._hash_descriptor  # noqa: SLF001 - deterministic race injection.
    hash_calls = 0

    def hash_then_mutate(descriptor: int) -> str:
        nonlocal hash_calls
        hash_calls += 1
        digest = original_hash(descriptor)
        if hash_calls == 3:
            earlier.write_bytes(b"zzzz")
        return digest

    monkeypatch.setattr(manifest, "_hash_descriptor", hash_then_mutate)

    with pytest.raises(manifest.ContractError, match="changed"):
        manifest.verify_collection(root, collection)


def test_require_verdict_eligible_rejects_provisional_contract() -> None:
    manifest = _manifest_module()

    with pytest.raises(manifest.ContractError, match="verdict_eligible"):
        manifest.require_verdict_eligible({"status": "provisional"})


def test_require_verdict_eligible_accepts_only_eligible_contract() -> None:
    manifest = _manifest_module()

    manifest.require_verdict_eligible({"status": "verdict_eligible"})
