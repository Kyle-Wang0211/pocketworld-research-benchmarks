#!/usr/bin/env python3
"""Canonical 9-gate scorer ported to the cap51 world (audit remediation: the
E-series had been running a 4-ruler subset; this restores the certified
battery). ARKit truth = per-frame priors from sfm_fed_frames.jsonl
(arkitCamFromWorldQwxyz/Txyz + center). score() logic imported VERBATIM from
fixtures_persist/score_gates.py (only the fixture-bound ARK global replaced).
"""
import json, sys
from pathlib import Path
import numpy as np

FP = "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/fixtures_persist"
ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
E22 = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/E22_rebirth_prototype"
FED = f"{ROOT}/data/pocketworld_captures/cap51/private_manifests/sfm_fed_frames.jsonl"

src = open(f"{FP}/score_gates.py").read()
anchor = "ARK = arkit_centers_R()"
assert anchor in src
src = src.replace(anchor, "ARK = {}")
mod = {"__name__": "score_gates_cap51"}
exec(compile(src, "score_gates.py", "exec"), mod)

def quat_to_R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])

ark = {}
for line in open(FED):
    j = json.loads(line)
    R = quat_to_R(j["arkitCamFromWorldQwxyz"])          # cam_from_world
    C = np.asarray(j["arkitCameraCenterWorld"], float)
    ark[f"frame_{j['frameId']:06d}.jpg"] = (C, R.T @ np.diag([1.,-1.,-1.]))           # (center, world_from_cam)
mod["ARK"].update(ark)
print(f"ARKit truth: {len(ark)} frames from fed jsonl")

ARMS = [
    ("baseline", f"{ROOT}/experiments/rs_replication_exec_2026-07-19/E9_birth_alias/runs/cap51_off_r1"),
    ("R-sift-2v", f"{E22}/rebirth_sift_2v"),
    ("R-loftr-2v", f"{E22}/rebirth_loftr_2v"),
    ("R-sift-mv", f"{E22}/rebirth_sift"),
]
res = {}
for tag, p in ARMS:
    print(f"== scoring {tag}")
    res[tag] = mod["score"](p, tag)
json.dump(res, open(f"{E22}/nine_gates_cap51.json", "w"), indent=1)

base = res["baseline"]
KEYS = ["reproj_median_px", "sv_surface_var", "tri_angle_deg", "weak_track_pct",
        "sphere_fit_mm", "floor_thick_mm", "arkit_pos_mm", "arkit_orient_deg", "point_count"]
print(f"\n{'gate':<18}" + "".join(f"{t:>14}" for t, _ in ARMS))
for k in KEYS:
    print(f"{k:<18}" + "".join(f"{res[t].get(k, float('nan')):>14.4f}" for t, _ in ARMS))
print("\n硬门判定(vs baseline):")
for tag, _ in ARMS[1:]:
    r = res[tag]
    checks = {
        "g2 sv<=0.0630": r["sv_surface_var"] <= 0.0630,
        "g3 tri>=0.97x": r["tri_angle_deg"] >= 0.97 * base["tri_angle_deg"],
        "g9 n>=0.97x": r["point_count"] >= 0.97 * base["point_count"],
    }
    print(tag, checks)
