#!/usr/bin/env python3
"""Merge independent wall proposal sources before image-only ownership.

The merge grants no point-birth authority.  Every wall is converted back to a
proposal and must win the downstream multi-view owner selector.  Keeping the
legacy sparse Top-K source beside the camera-envelope source makes the new
proposal mechanism additive: it may recover a wall the old source missed, but
it cannot silently remove an old candidate before both see the same evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_source(value: str) -> tuple[str, Path]:
    alias, separator, raw_path = value.partition("=")
    if not separator or not alias or not raw_path:
        raise argparse.ArgumentTypeError("source must be ALIAS=PATH")
    if not alias.replace("_", "").isalnum():
        raise argparse.ArgumentTypeError("source alias must be alphanumeric/underscore")
    return alias, Path(raw_path)


def unit_normal(floor: dict) -> np.ndarray:
    normal = np.asarray(floor["normal"], dtype=np.float64)
    norm = float(np.linalg.norm(normal))
    if not np.isfinite(norm) or norm <= 0.0:
        raise RuntimeError("invalid floor normal")
    return normal / norm


def assert_same_floor(reference: dict, candidate: dict, source: Path) -> None:
    left = unit_normal(reference)
    right = unit_normal(candidate)
    dot = float(left @ right)
    left_value = float(reference["plane_value_n_dot_x"])
    right_value = float(candidate["plane_value_n_dot_x"])
    if dot < 0.999:
        raise RuntimeError(f"floor normal mismatch in {source}: dot={dot}")
    if abs(left_value - right_value) > 0.03:
        raise RuntimeError(
            f"floor value mismatch in {source}: {left_value} vs {right_value}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", action="append", type=parse_source, required=True)
    parser.add_argument("--incumbent-alias", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.source) < 2:
        raise ValueError("at least two independent candidate sources are required")

    aliases = [alias for alias, _ in args.source]
    if len(set(aliases)) != len(aliases):
        raise ValueError("candidate source aliases must be unique")
    unknown_incumbents = set(args.incumbent_alias) - set(aliases)
    if unknown_incumbents:
        raise ValueError(f"unknown incumbent aliases: {sorted(unknown_incumbents)}")

    inputs = []
    surfaces = []
    floor = None
    seen_ids: set[str] = set()
    for alias, path in args.source:
        document = json.loads(path.read_text())
        source_floor = document["floor"]
        if floor is None:
            floor = source_floor
        else:
            assert_same_floor(floor, source_floor, path)
        source_hash = sha256(path)
        wall_count = 0
        for original in document.get("surfaces", []):
            if original.get("kind") != "wall":
                continue
            wall_count += 1
            surface = dict(original)
            original_id = str(surface["surface_id"])
            merged_id = f"{alias}__{original_id}"
            if merged_id in seen_ids:
                raise RuntimeError(f"duplicate merged surface id: {merged_id}")
            seen_ids.add(merged_id)
            surface.update(
                {
                    "surface_id": merged_id,
                    "candidate_source_alias": alias,
                    "candidate_source_surface_id": original_id,
                    "candidate_source_sha256": source_hash,
                    "candidate_source_certified_for_generation": bool(
                        alias in args.incumbent_alias
                        and original.get("certified_for_generation", False)
                    ),
                    "certified_for_generation": False,
                    "proposal_only": True,
                }
            )
            surfaces.append(surface)
        inputs.append(
            {
                "alias": alias,
                "path": str(path),
                "sha256": source_hash,
                "wall_candidate_count": wall_count,
            }
        )

    if floor is None or not surfaces:
        raise RuntimeError("merged candidate set is empty")
    result = {
        "schema": "aether_wall_candidate_union_v2",
        "method": "candidate_source_union_before_multiview_owner_selection",
        "birth_authority": False,
        "incumbent_aliases": sorted(set(args.incumbent_alias)),
        "forbidden_inputs_consumed": {
            "reference_plane": False,
            "learned_matcher": False,
            "lidar": False,
            "scene_depth": False,
        },
        "inputs": inputs,
        "floor": floor,
        "surface_count": len(surfaces),
        "surfaces": surfaces,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "surface_count": len(surfaces),
                "source_counts": {
                    item["alias"]: item["wall_candidate_count"] for item in inputs
                },
                "birth_authority": False,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
