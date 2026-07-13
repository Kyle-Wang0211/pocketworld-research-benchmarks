from __future__ import annotations

import importlib
import json
import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
    from types import ModuleType


def _cli_module() -> ModuleType:
    return importlib.import_module("pocketworld_contract.cli")


def test_cli_build_verify_and_gate_verdict(tmp_path: Path) -> None:
    cli = _cli_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "capture.jpg").write_bytes(b"fixture")
    output = tmp_path / "manifest.json"

    assert (
        cli.main(
            [
                "build",
                str(root),
                "--collection",
                "fixture",
                "--license-status",
                "license-reviewed",
                "--platform-qualification",
                "local-only",
                "--evidence-role",
                "diagnostic",
                "--lineage-contains-noncommercial",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert output.read_bytes().endswith(b"\n")
    asset = json.loads(output.read_text(encoding="utf-8"))["assets"][0]
    assert asset["role"] == "capture_image"
    assert asset["license_status"] == "license-reviewed"
    assert asset["platform_qualification"] == "local-only"
    assert asset["evidence_role"] == "diagnostic"
    assert asset["lineage_contains_noncommercial"] is True
    assert "commercial_eligibility" not in asset
    assert cli.main(["verify", str(root), str(output)]) == 0

    contract = tmp_path / "contract.json"
    contract.write_text('{"status":"verdict_eligible"}\n', encoding="utf-8")
    assert cli.main(["gate-verdict", str(contract)]) == 0


@pytest.mark.parametrize("output_route", ["direct", "symlink"])
def test_cli_build_rejects_output_inside_collection_root(
    tmp_path: Path,
    output_route: str,
) -> None:
    cli = _cli_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "capture.jpg").write_bytes(b"fixture")
    output_parent = root
    if output_route == "symlink":
        output_parent = tmp_path / "asset-alias"
        output_parent.symlink_to(root, target_is_directory=True)
    output = output_parent / "manifest.json"

    result = cli.main(
        [
            "build",
            str(root),
            "--collection",
            "fixture",
            "--license-status",
            "license-reviewed",
            "--platform-qualification",
            "local-only",
            "--evidence-role",
            "diagnostic",
            "--output",
            str(output),
        ]
    )

    assert result == 2
    assert not (root / "manifest.json").exists()


def test_cli_build_rejects_case_only_output_alias_inside_collection_root(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    root = tmp_path / "Assets"
    root.mkdir()
    asset = root / "Manifest.JSON"
    original_bytes = b"collection-asset"
    asset.write_bytes(original_bytes)
    alias_root = tmp_path / "aSSETS"
    if not alias_root.exists() or not root.samefile(alias_root):
        pytest.skip("test volume is case-sensitive")

    result = cli.main(
        [
            "build",
            str(root),
            "--collection",
            "fixture",
            "--license-status",
            "license-reviewed",
            "--platform-qualification",
            "local-only",
            "--evidence-role",
            "diagnostic",
            "--output",
            str(alias_root / "mANIFEST.json"),
        ]
    )

    assert result == 2
    assert asset.read_bytes() == original_bytes


def test_cli_build_atomically_replaces_outside_hardlink_without_mutating_asset(
    tmp_path: Path,
) -> None:
    cli = _cli_module()
    root = tmp_path / "assets"
    root.mkdir()
    asset = root / "capture.jpg"
    original_bytes = b"collection-asset"
    asset.write_bytes(original_bytes)
    original_stat = asset.stat()
    output = tmp_path / "manifest.json"
    os.link(asset, output)

    result = cli.main(
        [
            "build",
            str(root),
            "--collection",
            "fixture",
            "--license-status",
            "license-reviewed",
            "--platform-qualification",
            "local-only",
            "--evidence-role",
            "diagnostic",
            "--output",
            str(output),
        ]
    )

    assert result == 0
    assert asset.read_bytes() == original_bytes
    current_stat = asset.stat()
    assert (current_stat.st_dev, current_stat.st_ino, current_stat.st_size) == (
        original_stat.st_dev,
        original_stat.st_ino,
        original_stat.st_size,
    )
    assert asset.stat().st_ino != output.stat().st_ino
    assert json.loads(output.read_text(encoding="utf-8"))["assets"][0]["path"] == "capture.jpg"
    assert cli.main(["verify", str(root), str(output)]) == 0


def test_cli_build_rechecks_output_parent_ancestry_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "capture.jpg").write_bytes(b"fixture")
    output_parent = tmp_path / "output"
    output_parent.mkdir()
    output = output_parent / "manifest.json"
    moved_parent = root / "moved-output"
    original_build = cli.build_collection

    def build_then_move_parent(*args: object, **kwargs: object) -> dict[str, object]:
        collection = original_build(*args, **kwargs)
        output_parent.rename(moved_parent)
        return collection

    monkeypatch.setattr(cli, "build_collection", build_then_move_parent)

    result = cli.main(
        [
            "build",
            str(root),
            "--collection",
            "fixture",
            "--license-status",
            "license-reviewed",
            "--platform-qualification",
            "local-only",
            "--evidence-role",
            "diagnostic",
            "--output",
            str(output),
        ]
    )

    assert result == 2
    assert not (moved_parent / "manifest.json").exists()


def test_cli_build_rechecks_output_parent_after_temporary_file_fsync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "capture.jpg").write_bytes(b"fixture")
    output_parent = tmp_path / "output"
    output_parent.mkdir()
    output = output_parent / "manifest.json"
    moved_parent = root / "moved-output"
    original_fsync = cli.os.fsync
    moved = False

    def fsync_then_move_parent(descriptor: int) -> None:
        nonlocal moved
        original_fsync(descriptor)
        if not moved:
            output_parent.rename(moved_parent)
            moved = True

    monkeypatch.setattr(cli.os, "fsync", fsync_then_move_parent)

    result = cli.main(
        [
            "build",
            str(root),
            "--collection",
            "fixture",
            "--license-status",
            "license-reviewed",
            "--platform-qualification",
            "local-only",
            "--evidence-role",
            "diagnostic",
            "--output",
            str(output),
        ]
    )

    assert result == 2
    assert not (moved_parent / "manifest.json").exists()
    assert list(moved_parent.glob(".pocketworld-contract-*.tmp")) == []


def test_cli_build_rejects_root_identity_swap_before_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "original.jpg").write_bytes(b"original")
    replacement_root = tmp_path / "replacement-assets"
    replacement_root.mkdir()
    (replacement_root / "replacement.jpg").write_bytes(b"replacement")
    output_parent = tmp_path / "output"
    output_parent.mkdir()
    output = output_parent / "manifest.json"
    moved_parent = root / "moved-output"
    original_root = tmp_path / "original-assets"
    original_build = cli.build_collection

    def swap_root_then_build(*args: object, **kwargs: object) -> dict[str, object]:
        root.rename(original_root)
        replacement_root.rename(root)
        output_parent.rename(moved_parent)
        return original_build(*args, **kwargs)

    monkeypatch.setattr(cli, "build_collection", swap_root_then_build)

    result = cli.main(
        [
            "build",
            str(root),
            "--collection",
            "fixture",
            "--license-status",
            "license-reviewed",
            "--platform-qualification",
            "local-only",
            "--evidence-role",
            "diagnostic",
            "--output",
            str(output),
        ]
    )

    assert result == 2
    assert not (moved_parent / "manifest.json").exists()


def test_cli_build_replace_failure_preserves_output_and_cleans_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cli = _cli_module()
    root = tmp_path / "assets"
    root.mkdir()
    (root / "capture.jpg").write_bytes(b"fixture")
    output = tmp_path / "manifest.json"
    original_output = b"existing-output"
    output.write_bytes(original_output)

    def fail_replace(*_args: object, **_kwargs: object) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(cli.os, "replace", fail_replace)

    result = cli.main(
        [
            "build",
            str(root),
            "--collection",
            "fixture",
            "--license-status",
            "license-reviewed",
            "--platform-qualification",
            "local-only",
            "--evidence-role",
            "diagnostic",
            "--output",
            str(output),
        ]
    )

    assert result == 2
    assert output.read_bytes() == original_output
    assert list(tmp_path.glob(".pocketworld-contract-*.tmp")) == []
