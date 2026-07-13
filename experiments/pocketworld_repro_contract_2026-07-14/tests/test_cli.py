from __future__ import annotations

import importlib
import json
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
