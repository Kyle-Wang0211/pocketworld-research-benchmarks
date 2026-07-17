#!/usr/bin/env python3
"""U3 #7 -- off-plane multi-depth competition diagnostic for the pure-A floor
plane-sweep (does the flattened-chair false positive die under depth competition?).

DIAGNOSTIC ONLY. This does not mint product points, choose a production threshold,
or make a birth decision. It replays the frozen f2fc9a1 accepted floor points and,
for each one, runs the pinned depth-competition machinery that ALREADY exists in
``sweep_surface`` but is disabled in the certified config
(``depth_competition_offsets_m == ()`` is the root cause identified in U3 #5).

For every accepted floor grid point (offset 0 along the certified floor normal) we
score parallel hypotheses at +/- offsets along that normal, reusing the pinned
``score_point_hypothesis`` / ``unique_depth_winner`` semantics VERBATIM (the module
is imported from the pinned git blob, never modified). A floor point "survives"
(is born) only if the floor depth uniquely wins every off-plane competitor by the
required margin; otherwise the floor cell is left as a HOLE (an off-plane structure,
e.g. the chair, is present).

Populations tested:
  * chair ROI  : every frozen accepted point inside the flattened-chair ROI
                 X in [0.25,1.05], Z in [-1.70,-0.55].
  * clean floor: a deterministic warm-brown (wood) subsample OUTSIDE the ROI, to
                 measure collateral damage (true-floor retention) of the filter.

Reported at three decision rules over the same scored competitors:
  * pinned      : center_views >= alt_views AND center_ncc >= alt_ncc + 0.02
                  (exactly the certified ``unique_depth_winner`` at the default
                  ``depth_ncc_margin``).
  * margin_0.05 : same view-dominance rule but the task's suggested 0.05 ncc margin.
  * ncc_only_005: drop the view-count rule; floor survives iff it beats every
                  competitor by >= 0.05 ncc regardless of view counts.

No matcher, LoFTR, learned feature, or detector-free output is read.
"""
from __future__ import annotations

import gc
import hashlib
import json
import math
import resource
import subprocess
import sys
import time
import types
from pathlib import Path

import numpy as np

REPO = Path(
    "/Users/kaidongwang/.config/superpowers/worktrees/"
    "pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
)
PINNED_REVISION = "f2fc9a1"
PINNED_SOURCE_PATH = (
    "experiments/floor_plane_sweep_densifier_2026-07-13/fr_planesweep_wall_ceiling.py"
)
PINNED_SOURCE_SHA256 = (
    "d34a8bd3f76d5d11c8ad1917bb53339306a17595fca3fbf5609bacb7863498e2"
)
EXPECTED_UNION_PLY_SHA256 = (
    "fdf5b105e55243d1b6599f640a2fe61727ca3c81197c56644f5304b3927d4c34"
)
EXPECTED_UNION_POINTS = 13_488
SURFACE_ID = "floor_0"

OUT_DIR = REPO / "experiments/u3_merge_prototypes_2026-07-18/07_offplane_depth_competition"
UNION_PLY = (
    REPO
    / "experiments/u3_merge_prototypes_2026-07-18/05_median_fusion/union_baseline.ply"
)

# Certified adapter CONFIG, verbatim, EXCEPT depth_competition_offsets_m which we
# populate here to actually run the competition that the certified run leaves off.
CONFIG = {
    "grid_m": 0.01, "patch_n": 7, "patch_radius_m": 0.015, "min_std": 6.0,
    "ncc_min": 0.70, "min_views": 3, "min_parallax_deg": 5.0, "max_views": 48,
    "base_max_views": 10, "rescue_min_ncc": 0.8500471980155323,
    "rescue_min_parallax_deg": 10.241134230890212, "rescue_min_views": 3,
    "max_graze_deg": 72.0, "image_margin_px": 2.0, "tile_points": 256,
    "image_cache_images": 64, "depth_competition_offsets_m": (),
    "depth_ncc_margin": 0.02,
}

# Off-plane hypotheses along the certified floor normal (both directions; fine
# near the surface where a chair seat/edge would sit, coarser far away).
DEPTH_OFFSETS_M = (
    0.03, 0.05, 0.08, 0.12, 0.18, 0.25, 0.35, 0.50,
    -0.03, -0.05, -0.08, -0.12, -0.18, -0.25, -0.35, -0.50,
)

# Chair/treadmill flattened-false-positive ROI (top-down X-Z), lower-right object.
ROI = dict(X0=0.25, X1=1.05, Z0=-1.70, Z1=-0.55)

# Decision-rule margins.
PINNED_MARGIN = 0.02
TASK_MARGIN = 0.05

CLEAN_SUBSAMPLE_STRIDE = 14   # deterministic stride over warm-brown out-of-ROI pts
MEM_GUARD_GB = 6.0

# frozen-replay tolerances matching union PLY rounding (views/candidate exact,
# parallax 5 decimals, zncc 6 decimals) -- same as the height probe.
REPLAY_TOL = np.asarray([0.0, 5.1e-5, 5.1e-7, 0.0])


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as s:
        for blk in iter(lambda: s.read(1 << 20), b""):
            d.update(blk)
    return d.hexdigest()


def rss_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


def mem_guard() -> None:
    if rss_gb() > MEM_GUARD_GB:
        raise MemoryError(f"RSS {rss_gb():.2f} GB exceeded {MEM_GUARD_GB} GB guard")


def load_pinned_module() -> types.ModuleType:
    payload = subprocess.check_output(
        ["git", "-C", str(REPO), "show", f"{PINNED_REVISION}:{PINNED_SOURCE_PATH}"]
    )
    actual = hashlib.sha256(payload).hexdigest()
    if actual != PINNED_SOURCE_SHA256:
        raise RuntimeError(f"pinned source SHA mismatch: {actual}")
    name = "pocketworld_pinned_planesweep_f2fc9a1"
    module = types.ModuleType(name)
    module.__file__ = f"git:{PINNED_REVISION}:{PINNED_SOURCE_PATH}"
    sys.modules[name] = module
    exec(compile(payload, module.__file__, "exec"), module.__dict__)
    return module


def default_inputs() -> dict[str, Path]:
    run = REPO / (
        "experiments/floor_plane_sweep_densifier_2026-07-13/"
        "runs/cap50_pure_a_wall_ceiling_20260714"
    )
    capture = REPO / "data/pocketworld_captures/cap50"
    return {
        "frame_meta": capture / "private_manifests/subset_meta_cap50full.json",
        "ledger": capture / "private_manifests/sfm_fed_frames.jsonl",
        "photos": capture / "raw/photos_highres",
        "planes": run / "structural_planes_v5_floor.json",
    }


def read_union_ply(path: Path):
    xs, ys, zs, r, g, b, meta = [], [], [], [], [], [], []
    with path.open() as f:
        hdr = True
        for line in f:
            if hdr:
                if line.startswith("end_header"):
                    hdr = False
                continue
            t = line.split()
            xs.append(float(t[0])); ys.append(float(t[1])); zs.append(float(t[2]))
            r.append(int(t[3])); g.append(int(t[4])); b.append(int(t[5]))
            # nviews parallax_deg zncc_median candidate_views
            meta.append([float(t[6]), float(t[7]), float(t[8]), float(t[9])])
    xyz = np.column_stack([xs, ys, zs]).astype(np.float64)
    rgb = np.column_stack([r, g, b]).astype(np.int64)
    return xyz, rgb, np.asarray(meta, dtype=np.float64)


def match_grid_point(grid_lookup, grid, ply_xyz, tol_m=2e-7):
    """Map a 7-decimal PLY vertex back to its exact float64 grid coordinate.
    The pinned sweep scores the exact grid point; using the PLY-rounded position
    perturbs projections by ~5e-8 m and the ZNCC by ~5e-6, so replay must use the
    exact coordinate (same approach as the height-hypothesis probe)."""
    idx = grid_lookup.get(tuple(np.round(ply_xyz, 7)))
    if idx is None:
        d = np.linalg.norm(grid - ply_xyz, axis=1)
        idx = int(np.argmin(d))
    err = float(np.linalg.norm(grid[idx] - ply_xyz))
    if err > tol_m:
        raise ValueError(f"PLY vertex does not map to floor grid: {err} m")
    return grid[idx], err


def in_roi(x, z):
    return (x >= ROI["X0"]) & (x <= ROI["X1"]) & (z >= ROI["Z0"]) & (z <= ROI["Z1"])


def is_false_positive(rgb):
    """Chair/treadmill = cool desaturated (blue channel not much below red);
    wood floor = warm brown (red clearly dominant). Reused verbatim from the
    median-fusion comparison so the FP definition is identical across prototypes."""
    r, g, b = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    return b >= (r - 8)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=", 1)[1])

    module = load_pinned_module()
    paths = default_inputs()
    planes = json.loads(paths["planes"].read_text())
    surfaces = module.select_surfaces(planes, [SURFACE_ID], False)
    floor_surface = surfaces[0]
    floor = planes["floor"]
    config = module.SweepConfig(**CONFIG)
    normal = np.asarray(floor_surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    offsets = module.patch_offsets(floor_surface, floor, config)

    frames = module.load_frames(paths["frame_meta"], paths["ledger"], paths["photos"])
    if len(frames) != 115:
        raise RuntimeError(f"expected 115 frames, got {len(frames)}")

    union_sha = sha256_file(UNION_PLY)
    if union_sha != EXPECTED_UNION_PLY_SHA256:
        raise RuntimeError(f"union baseline SHA mismatch: {union_sha}")
    uxyz, urgb, umeta = read_union_ply(UNION_PLY)
    if len(uxyz) != EXPECTED_UNION_POINTS:
        raise RuntimeError(f"union point count {len(uxyz)}")

    # Exact grid coordinates (PLY xyz is 7-decimal rounded; pinned scores exact).
    grid = module.surface_grid(floor_surface, floor, config.grid_m, 0.0)
    grid_lookup = {tuple(np.round(p, 7)): i for i, p in enumerate(grid)}
    max_grid_err = 0.0

    ux, uy, uz = uxyz[:, 0], uxyz[:, 1], uxyz[:, 2]
    roi_mask = in_roi(ux, uz)
    fp_mask = is_false_positive(urgb)
    clean_mask = (~roi_mask) & (~fp_mask)  # wood floor outside chair ROI

    # Deterministic populations (kept in union-file / grid order for cache locality).
    roi_indices = np.flatnonzero(roi_mask)
    clean_all = np.flatnonzero(clean_mask)
    clean_indices = clean_all[::CLEAN_SUBSAMPLE_STRIDE]

    test = [(int(i), "roi") for i in roi_indices] + [
        (int(i), "clean") for i in clean_indices
    ]
    # process in ascending union index so the ImageCache stays warm along the grid.
    test.sort(key=lambda kv: kv[0])
    if limit is not None:
        test = test[:limit]

    print(
        f"[{time.perf_counter()-t0:.1f}s] loaded {len(frames)} frames; "
        f"union {len(uxyz)} pts (sha {union_sha[:12]}); "
        f"testing {len(test)} points "
        f"(roi {int(roi_mask.sum())}, clean subsample {len(clean_indices)} "
        f"of {len(clean_all)}); offsets {len(DEPTH_OFFSETS_M)}",
        flush=True,
    )

    image_cache = module.ImageCache(
        frames, max(config.image_cache_images, config.max_views)
    )
    base_count = (
        min(config.base_max_views, config.max_views)
        if config.base_max_views > 0
        else config.max_views
    )

    rows = []
    replay_mismatches = 0
    n_done = 0
    for uidx, population in test:
        point, grid_err = match_grid_point(grid_lookup, grid, uxyz[uidx])
        point = point.copy()
        max_grid_err = max(max_grid_err, grid_err)
        frozen_meta = umeta[uidx]

        visible, head_on, _ = module.project_centers(
            point[None, :], frames, normal, config
        )
        candidate = module.select_point_views(
            visible[:, 0], head_on[:, 0], config.max_views
        )
        images = image_cache.get_many(candidate) if candidate else {}
        base_candidate = candidate[:base_count]
        center, reason = module.score_point_hypothesis(
            point, offsets, frames, base_candidate, images, config
        )
        used_candidate = base_candidate
        arm = "base10"
        if center is None and base_count < config.max_views and len(candidate) > base_count:
            rescue, rescue_reason = module.score_point_hypothesis(
                point, offsets, frames, candidate, images, config
            )
            if rescue is not None and module.passes_rescue_gate(
                rescue, config.rescue_min_ncc,
                config.rescue_min_parallax_deg, config.rescue_min_views,
            ):
                center = rescue
                used_candidate = candidate
                arm = "rescue48"
        if center is None:
            # frozen accepted point failed to replay -> hard error, this must not happen
            raise RuntimeError(
                f"frozen accepted union point {uidx} failed center replay: {reason}"
            )

        center_meta = np.asarray(
            [center["views"], center["parallax"], center["ncc"],
             center["candidate_views"]], dtype=np.float64
        )
        if np.any(np.abs(center_meta - frozen_meta) > REPLAY_TOL):
            replay_mismatches += 1

        # ---- off-plane depth competition (pinned semantics, verbatim) ----
        alternatives = []          # (views, ncc) for scoreable competitors
        alt_detail = []            # per-offset record
        for depth_offset in DEPTH_OFFSETS_M:
            shifted = point + normal * depth_offset
            alt_visible, _, _ = module.project_centers(
                shifted[None, :], frames, normal, config
            )
            alt_candidate = [i for i in used_candidate if alt_visible[i, 0]]
            alternative, alt_reason = module.score_point_hypothesis(
                shifted, offsets, frames, alt_candidate, images, config
            )
            if alternative is not None:
                alternatives.append((alternative["views"], alternative["ncc"]))
                alt_detail.append({
                    "offset_m": depth_offset,
                    "views": int(alternative["views"]),
                    "ncc": float(alternative["ncc"]),
                    "parallax_deg": float(alternative["parallax"]),
                    "reason": None,
                })
            else:
                alt_detail.append({
                    "offset_m": depth_offset, "views": None, "ncc": None,
                    "parallax_deg": None, "reason": alt_reason,
                })

        c_views = int(center["views"])
        c_ncc = float(center["ncc"])

        # pinned rule (unique_depth_winner at 0.02)
        survives_pinned, observed_margin = module.unique_depth_winner(
            c_views, c_ncc, alternatives, PINNED_MARGIN
        )
        # view-dominance + 0.05 margin
        survives_m05, _ = module.unique_depth_winner(
            c_views, c_ncc, alternatives, TASK_MARGIN
        )
        # ncc-only 0.05 (drop the view-count dominance requirement)
        if alternatives:
            best_alt_ncc = max(ncc for _, ncc in alternatives)
            survives_ncc05 = all(
                c_ncc >= ncc + TASK_MARGIN for _, ncc in alternatives
            )
        else:
            best_alt_ncc = None
            survives_ncc05 = True

        # best (strongest) competitor for reporting
        best_alt = None
        if alt_detail:
            scoreable = [a for a in alt_detail if a["ncc"] is not None]
            if scoreable:
                best_alt = max(scoreable, key=lambda a: a["ncc"])

        rows.append({
            "union_index": uidx,
            "population": population,
            "xyz_m": [float(v) for v in point],
            "rgb_u8": [int(v) for v in urgb[uidx]],
            "is_false_positive_color": bool(fp_mask[uidx]),
            "arm": arm,
            "floor_views": c_views,
            "floor_ncc": c_ncc,
            "floor_parallax_deg": float(center["parallax"]),
            "candidate_views": int(center["candidate_views"]),
            "n_scoreable_competitors": len(alternatives),
            "best_competitor": best_alt,
            "best_competitor_ncc": best_alt_ncc,
            "floor_minus_best_competitor_ncc": (
                None if best_alt_ncc is None else float(c_ncc - best_alt_ncc)
            ),
            "survives_pinned_0.02": bool(survives_pinned),
            "survives_viewdom_0.05": bool(survives_m05),
            "survives_ncconly_0.05": bool(survives_ncc05),
            "offsets": alt_detail,
        })
        n_done += 1
        if n_done % 200 == 0:
            mem_guard()
            print(f"[{time.perf_counter()-t0:.1f}s] {n_done}/{len(test)} "
                  f"RSS {rss_gb():.2f}GB mismatches {replay_mismatches}", flush=True)

    gc.collect()

    # ---------------- aggregate ----------------
    def agg(pop_rows):
        n = len(pop_rows)
        fp = [r for r in pop_rows if r["is_false_positive_color"]]
        out = {"n": n, "n_fp_color": len(fp)}
        for rule in ("survives_pinned_0.02", "survives_viewdom_0.05",
                     "survives_ncconly_0.05"):
            survive = sum(1 for r in pop_rows if r[rule])
            hole = n - survive
            fp_survive = sum(1 for r in fp if r[rule])
            fp_hole = len(fp) - fp_survive
            out[rule] = {
                "survive": survive,
                "hole": hole,
                "hole_rate": hole / n if n else 0.0,
                "fp_survive": fp_survive,
                "fp_hole": fp_hole,
                "fp_kill_rate": fp_hole / len(fp) if fp else 0.0,
            }
        return out

    roi_rows = [r for r in rows if r["population"] == "roi"]
    clean_rows = [r for r in rows if r["population"] == "clean"]

    stats = {
        "schema": "u3_offplane_depth_competition_v1",
        "diagnostic_only": True,
        "capture": "cap50",
        "surface_id": SURFACE_ID,
        "roi_box_xz": ROI,
        "depth_offsets_m": list(DEPTH_OFFSETS_M),
        "n_offsets": len(DEPTH_OFFSETS_M),
        "pinned_margin": PINNED_MARGIN,
        "task_margin": TASK_MARGIN,
        "union_total": int(len(uxyz)),
        "union_roi_points": int(roi_mask.sum()),
        "union_roi_fp_color": int((roi_mask & fp_mask).sum()),
        "union_clean_out_of_roi": int(clean_mask.sum()),
        "clean_subsample_stride": CLEAN_SUBSAMPLE_STRIDE,
        "replay_center_mismatches": replay_mismatches,
        "max_ply_to_grid_error_m": max_grid_err,
        "chair_roi": agg(roi_rows),
        "clean_floor_subsample": agg(clean_rows),
    }

    # per-offset kill attribution (pinned rule): among ROI FP points that are
    # holed, which offset was the strongest competitor.
    offset_kill = {f"{o:+.2f}": 0 for o in DEPTH_OFFSETS_M}
    for r in roi_rows:
        if r["is_false_positive_color"] and not r["survives_pinned_0.02"]:
            bc = r["best_competitor"]
            if bc is not None:
                offset_kill[f"{bc['offset_m']:+.2f}"] += 1
    stats["roi_fp_hole_best_offset_attribution_pinned"] = offset_kill

    (OUT_DIR / "stats.json").write_text(
        json.dumps(stats, indent=2, sort_keys=True) + "\n"
    )

    # jsonl (canonical, deterministic)
    def canon(v):
        return json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    (OUT_DIR / "depth_competition.jsonl").write_text(
        "".join(canon(r) + "\n" for r in rows)
    )

    # ---------------- write survivor / hole PLYs for the ROI ----------------
    def write_ply(path, idx_list, meta_flag):
        with path.open("w", encoding="utf-8") as s:
            s.write("ply\nformat ascii 1.0\n")
            s.write(f"element vertex {len(idx_list)}\n")
            s.write("property float x\nproperty float y\nproperty float z\n")
            s.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
            s.write("property float survives_pinned\nend_header\n")
            for r in idx_list:
                p = r["xyz_m"]; c = r["rgb_u8"]
                s.write(f"{p[0]:.7f} {p[1]:.7f} {p[2]:.7f} "
                        f"{c[0]} {c[1]} {c[2]} {1.0 if r[meta_flag] else 0.0:.0f}\n")

    write_ply(OUT_DIR / "roi_all_scored.ply", roi_rows, "survives_pinned_0.02")
    write_ply(
        OUT_DIR / "roi_survivors_pinned.ply",
        [r for r in roi_rows if r["survives_pinned_0.02"]],
        "survives_pinned_0.02",
    )
    write_ply(
        OUT_DIR / "roi_holes_pinned.ply",
        [r for r in roi_rows if not r["survives_pinned_0.02"]],
        "survives_pinned_0.02",
    )

    manifest = {
        "schema": "u3_offplane_depth_competition_manifest_v1",
        "diagnostic_only": True,
        "candidate_points_added": 0,
        "candidate_points_removed": 0,
        "thresholds_selected": False,
        "birth_decisions_made": False,
        "capture": "cap50",
        "surface_id": SURFACE_ID,
        "generator_revision": PINNED_REVISION,
        "generator_source_sha256": PINNED_SOURCE_SHA256,
        "union_ply": str(UNION_PLY),
        "union_ply_sha256": union_sha,
        "config": {k: (list(v) if isinstance(v, tuple) else v)
                   for k, v in CONFIG.items()},
        "depth_offsets_m": list(DEPTH_OFFSETS_M),
        "n_test_points": len(rows),
        "elapsed_s": time.perf_counter() - t0,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "peak_loaded_image_bytes": int(image_cache.peak_bytes),
        "decoded_image_loads": int(image_cache.loads),
        "outputs": {},
    }
    for name in ("stats.json", "depth_competition.jsonl", "roi_all_scored.ply",
                 "roi_survivors_pinned.ply", "roi_holes_pinned.ply"):
        p = OUT_DIR / name
        if p.exists():
            manifest["outputs"][name] = sha256_file(p)
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(stats, indent=2, sort_keys=True))
    print(f"[{time.perf_counter()-t0:.1f}s] done; RSS {rss_gb():.2f}GB "
          f"loads {image_cache.loads} peakimg {image_cache.peak_bytes/1e9:.2f}GB")


if __name__ == "__main__":
    main()
