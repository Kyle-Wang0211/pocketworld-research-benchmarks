#!/usr/bin/env python3
"""E22-s3: full re-birth against frozen refined poses (pycolmap point_triangulator
semantics; poses constant by construction -> E21 pose-warp confound = 0).

Discipline = 100% COLMAP official defaults (create/continue 2.0deg angular,
filter 4px / min tri 1.5deg, internal retriangulation + global BA refinement
loop via ba_global_max_refinements). No invented numbers.

Usage: e22_s3_rebirth.py <db_path> <out_dir>
Pose source: E9 off_r1 replay model (production-recipe refined, device gauge).
"""
import os, shutil, sys
import pycolmap

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
MODEL = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/E9_birth_alias/runs/cap51_off_r1"
db_path, out_dir = sys.argv[1], sys.argv[2]
os.makedirs(out_dir, exist_ok=True)

rec = pycolmap.Reconstruction(MODEL)
print(f"loaded model: {rec.num_reg_images()} images, {rec.num_points3D()} points (will be cleared)")

opts = pycolmap.IncrementalPipelineOptions()
# COLMAP defaults throughout; make the refinement loop explicit + generous:
opts.ba_global_max_refinements = 5
opts.ba_global_function_tolerance = 0.0
# E22_ALLOW_2VIEW=1: RS tie-point semantics (>=2 obs) instead of COLMAP's
# default ignore_two_view_tracks=True (>=3-view only).
if os.environ.get("E22_ALLOW_2VIEW") == "1":
    opts.triangulation.ignore_two_view_tracks = False
dummy_images = os.path.join(out_dir, "_images_unused")
os.makedirs(dummy_images, exist_ok=True)
rec2 = pycolmap.triangulate_points(rec, db_path, dummy_images, out_dir,
                                   clear_points=True, options=opts)
print(f"rebirth: {rec2.num_points3D()} points, "
      f"mean track {rec2.compute_mean_track_length():.2f}, "
      f"mean reproj {rec2.compute_mean_reprojection_error():.3f}px")
