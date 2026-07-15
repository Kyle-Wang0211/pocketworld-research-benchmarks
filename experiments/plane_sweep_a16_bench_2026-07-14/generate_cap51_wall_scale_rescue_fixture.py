#!/usr/bin/env python3
"""Generate the cap51 wall_2/tile6 strict-rescue Dawn fixture."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE_PATH = HERE / "generate_wall_scale_rescue_fixture.py"
SPEC = importlib.util.spec_from_file_location("generate_wall_scale_rescue_fixture", BASE_PATH)
assert SPEC and SPEC.loader
BASE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BASE
SPEC.loader.exec_module(BASE)

BASE.PLANES = ROOT / (
    "experiments/floor_plane_sweep_densifier_2026-07-13/runs/"
    "cap51_pure_a_wall_holdout_20260715/structural_planes.json"
)
BASE.META = ROOT / (
    "experiments/floor_plane_sweep_densifier_2026-07-13/runs/"
    "cap51_pure_a_wall_holdout_20260715/frame_meta_cap51_available81.json"
)
BASE.LEDGER = ROOT / "data/pocketworld_captures/cap51/private_manifests/sfm_fed_frames.jsonl"
BASE.PHOTOS = Path(
    os.environ.get("POCKETWORLD_CAP51_PHOTOS", "/tmp/pocketworld_cap51_photos_20260715")
)
BASE.RESOURCES = HERE / "ios_dawn_wall_bench/Resources"
BASE.SURFACE_ID = "wall_2"
BASE.TILE_INDEX = 6
BASE.EXPECTED_BASELINE = []
BASE.EXPECTED_UNION = [16]


if __name__ == "__main__":
    BASE.main()
