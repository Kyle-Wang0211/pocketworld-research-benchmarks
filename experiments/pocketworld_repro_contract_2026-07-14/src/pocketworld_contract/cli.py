from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from pocketworld_contract.manifest import (
    ContractError,
    build_collection,
    canonical_json,
    require_verdict_eligible,
    verify_collection,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the local PocketWorld asset contract CLI."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)

    try:
        if arguments.command == "build":
            _require_output_outside_collection(arguments.root, arguments.output)
            manifest = build_collection(
                arguments.root,
                arguments.collection,
                license_status=arguments.license_status,
                platform_qualification=arguments.platform_qualification,
                evidence_role=arguments.evidence_role,
                lineage_contains_noncommercial=arguments.lineage_contains_noncommercial,
            )
            arguments.output.write_text(canonical_json(manifest), encoding="utf-8")
        elif arguments.command == "verify":
            verify_collection(arguments.root, _load_json_object(arguments.manifest))
            print("verified")
        elif arguments.command == "gate-verdict":
            require_verdict_eligible(_load_json_object(arguments.contract))
            print("verdict_eligible")
        else:  # pragma: no cover - argparse restricts command choices.
            parser.error(f"unknown command: {arguments.command}")
    except (ContractError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def _require_output_outside_collection(root: Path, output: Path) -> None:
    try:
        resolved_root = root.resolve(strict=True)
        resolved_output = output.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ContractError("unable to resolve collection root and output path") from exc
    if resolved_output == resolved_root or resolved_output.is_relative_to(resolved_root):
        raise ContractError("build output must be outside the collection root")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pocketworld-contract")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="build a deterministic collection manifest")
    build_parser.add_argument("root", type=Path)
    build_parser.add_argument("--collection", required=True)
    build_parser.add_argument("--license-status", required=True)
    build_parser.add_argument("--platform-qualification", required=True)
    build_parser.add_argument("--evidence-role", required=True)
    build_parser.add_argument("--lineage-contains-noncommercial", action="store_true")
    build_parser.add_argument("--output", required=True, type=Path)

    verify_parser = subparsers.add_parser("verify", help="verify an exact collection manifest")
    verify_parser.add_argument("root", type=Path)
    verify_parser.add_argument("manifest", type=Path)

    gate_parser = subparsers.add_parser(
        "gate-verdict",
        help="require a verdict-eligible research contract",
    )
    gate_parser.add_argument("contract", type=Path)
    return parser


def _load_json_object(path: Path) -> Mapping[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ContractError(f"JSON document must be an object: {path}")
    return loaded
