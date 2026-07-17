#!/usr/bin/env python3
"""U3 #5 -- COLMAP fusion.cc-style median fusion over the pure-A floor plane-sweep.

Replaces the plane-sweep's "union铺点" (every 1cm grid cell that individually
passes the multi-view ZNCC clique gate gets its own appended point) with a
StereoFusion-style median fusion that is faithful to COLMAP 4.1.0
``src/colmap/mvs/fusion.cc`` semantics:

  * region-growing BFS over surface measurements;
  * every measurement merged into a cluster must pass three gates against the
    cluster reference: relative depth error <= max_depth_error (1%),
    reprojection error <= max_reproj_error (2px), normal cos >= cos(10deg);
  * a cluster only emits a point when it collects >= min_num_pixels (5)
    mutually-consistent multi-view measurements;
  * the emitted point is the per-coordinate MEDIAN (not mean) of the cluster's
    3D positions / normals / colors;
  * every image pixel is fused at most once (fused_pixel_mask / single-pixel
    lock): once consumed it can neither seed nor join another cluster.

The union baseline is reproduced byte-for-byte from the pinned f2fc9a1
generator (13,488 points, PLY SHA fdf5b105...). The per-view measurements that
feed fusion are re-derived from the same pinned scoring path and asserted to
reproduce every accepted point's frozen (views, parallax, zncc, candidate_views)
tuple, so the fusion input is provably the same population as the union PLY.

Colorize is a bit-for-bit reuse of the historical/production path: the pinned
``bilinear_rgb`` samples each supporting view at the point's own full-image
projection (px*scale already baked into K), the point color is the cross-view
median of those samples, rounded on write.

No matcher, LoFTR, learned feature, or detector-free output is read.
"""
from __future__ import annotations

import gc
import hashlib
import json
import math
import os
import resource
import subprocess
import sys
import time
import types
from collections import defaultdict, OrderedDict
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Pinned generator identity (must match the U4 adapter).
# ---------------------------------------------------------------------------
REPO = Path("/Users/kaidongwang/.config/superpowers/worktrees/"
            "pocketworld_research_benchmarks/pocketworld-repro-contract-20260714")
PINNED_REVISION = "f2fc9a1"
PINNED_SOURCE_PATH = ("experiments/floor_plane_sweep_densifier_2026-07-13/"
                      "fr_planesweep_wall_ceiling.py")
PINNED_SOURCE_SHA256 = "d34a8bd3f76d5d11c8ad1917bb53339306a17595fca3fbf5609bacb7863498e2"
EXPECTED_HISTORICAL_PLY_SHA256 = (
    "fdf5b105e55243d1b6599f640a2fe61727ca3c81197c56644f5304b3927d4c34")
EXPECTED_HISTORICAL_POINTS = 13_488
SURFACE_ID = "floor_0"

# Pinned adapter CONFIG (verbatim from planesweep_candidate_adapter.py).
CONFIG = {
    "grid_m": 0.01, "patch_n": 7, "patch_radius_m": 0.015, "min_std": 6.0,
    "ncc_min": 0.70, "min_views": 3, "min_parallax_deg": 5.0, "max_views": 48,
    "base_max_views": 10, "rescue_min_ncc": 0.8500471980155323,
    "rescue_min_parallax_deg": 10.241134230890212, "rescue_min_views": 3,
    "max_graze_deg": 72.0, "image_margin_px": 2.0, "tile_points": 256,
    "image_cache_images": 64, "depth_competition_offsets_m": (),
    "depth_ncc_margin": 0.02,
}

# COLMAP StereoFusion defaults (src/colmap/mvs/fusion.h).
FUSION = {
    "min_num_pixels": 5,          # cluster must reach this many measurements
    "max_reproj_error_px": 2.0,   # reprojection gate
    "max_depth_error_rel": 0.01,  # relative depth gate (1%)
    "max_normal_error_deg": 10.0, # normal-angle gate
    "neighbor_radius_m": 0.03,    # region-grow candidate radius on the surface
}

OUT_DIR = REPO / "experiments/u3_merge_prototypes_2026-07-18/05_median_fusion"


def sha256_file(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as s:
        for blk in iter(lambda: s.read(1 << 20), b""):
            d.update(blk)
    return d.hexdigest()


def rss_gb() -> float:
    # macOS ru_maxrss is bytes.
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


def mem_guard(limit_gb: float = 6.0) -> None:
    if rss_gb() > limit_gb:
        raise MemoryError(f"RSS {rss_gb():.2f} GB exceeded guard {limit_gb} GB; aborting")


def load_pinned_module() -> types.ModuleType:
    payload = subprocess.check_output(
        ["git", "-C", str(REPO), "show", f"{PINNED_REVISION}:{PINNED_SOURCE_PATH}"])
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
    run = REPO / ("experiments/floor_plane_sweep_densifier_2026-07-13/"
                  "runs/cap50_pure_a_wall_ceiling_20260714")
    capture = REPO / "data/pocketworld_captures/cap50"
    return {
        "frame_meta": capture / "private_manifests/subset_meta_cap50full.json",
        "ledger": capture / "private_manifests/sfm_fed_frames.jsonl",
        "photos": capture / "raw/photos_highres",
        "planes": run / "structural_planes_v5_floor.json",
    }


# ---------------------------------------------------------------------------
# Instrumented scorer -- mirrors pinned score_point_hypothesis exactly, but also
# returns, per clique frame, the center pixel (point's own projection) and the
# center-sample RGB. The accepted point's numeric (views,parallax,ncc,candidate)
# tuple is bit-identical to the pinned path, which we assert downstream.
# ---------------------------------------------------------------------------
def score_traced(module, point, offsets, frames, candidate, images, config):
    if len(candidate) < config.min_views:
        return None, "few_geometry_views"
    samples = point[None, :] + offsets
    center_sample = len(offsets) // 2  # patch_offsets middle == (0,0) offset == point
    gray_patches, center_colors, center_pixels, used = [], [], [], []
    for fi in candidate:
        frame = frames[fi]
        cam = (frame.R @ samples.T).T + frame.t
        depth = cam[:, 2]
        if np.any(depth <= 0.05):
            continue
        homo = (frame.K @ cam.T).T
        xy = homo[:, :2] / depth[:, None]
        if (xy[:, 0].min() < 0 or xy[:, 0].max() > frame.width - 1
                or xy[:, 1].min() < 0 or xy[:, 1].max() > frame.height - 1):
            continue
        rgb = module.bilinear_rgb(images[fi], xy)
        gray = rgb @ module.GRAY_WEIGHTS
        if float(gray.std()) < config.min_std:
            continue
        gray_patches.append(gray)
        center_colors.append(rgb[len(rgb) // 2])
        center_pixels.append(xy[center_sample].copy())
        used.append(fi)
    if len(used) < config.min_views:
        return None, "few_texture_views"
    patches = np.stack(gray_patches)
    normalized = patches - patches.mean(axis=1, keepdims=True)
    normalized /= np.linalg.norm(normalized, axis=1, keepdims=True) + 1e-9
    ncc = normalized @ normalized.T
    np.fill_diagonal(ncc, 1.0)
    clique = module.largest_consistent_clique(ncc, config.ncc_min, config.min_views)
    if len(clique) < config.min_views:
        return None, "few_zncc_views"
    clique_local = [int(i) for i in clique]
    clique_frames = [used[i] for i in clique_local]
    rays = np.stack([point - frames[i].C for i in clique_frames])
    rays /= np.linalg.norm(rays, axis=1, keepdims=True) + 1e-12
    cosine = np.clip(rays @ rays.T, -1.0, 1.0)
    parallax = float(np.degrees(np.arccos(cosine)).max())
    if parallax < config.min_parallax_deg:
        return None, "low_parallax"
    sub = ncc[np.ix_(clique, clique)]
    pair_ncc = sub[np.triu_indices(len(clique), 1)]
    return {
        "views": len(clique),
        "parallax": parallax,
        "ncc": float(np.median(pair_ncc)),
        "candidate_views": len(candidate),
        "color": np.median(np.stack([center_colors[i] for i in clique_local]), axis=0),
        "clique_frames": clique_frames,
        "clique_pixels": [center_pixels[i] for i in clique_local],
        "clique_colors": [center_colors[i] for i in clique_local],
    }, None


def sweep_traced(module, surface, floor, frames, config):
    """Mirror pinned sweep_surface control flow, capturing per-accepted-point
    clique frames, per-view pixels, per-view colors. Returns accepted arrays and
    a parallel list of measurement dicts."""
    points = module.surface_grid(surface, floor, config.grid_m, 0.0)
    offsets = module.patch_offsets(surface, floor, config)
    normal = np.asarray(surface["normal"], dtype=np.float64)
    normal /= np.linalg.norm(normal)
    accepted_points, accepted_colors, accepted_meta, accepted_meas = [], [], [], []
    image_cache = module.ImageCache(frames, max(config.image_cache_images, config.max_views))
    for tile_start in range(0, len(points), config.tile_points):
        tile = points[tile_start:tile_start + config.tile_points]
        visible, head_on, _ = module.project_centers(tile, frames, normal, config)
        for li, point in enumerate(tile):
            candidate = module.select_point_views(
                visible[:, li], head_on[:, li], config.max_views)
            images = image_cache.get_many(candidate) if candidate else {}
            base_count = (min(config.base_max_views, config.max_views)
                          if config.base_max_views > 0 else config.max_views)
            base_candidate = candidate[:base_count]
            center, reason = score_traced(module, point, offsets, frames,
                                          base_candidate, images, config)
            if (center is None and base_count < config.max_views
                    and len(candidate) > base_count):
                rescue, _ = score_traced(module, point, offsets, frames,
                                         candidate, images, config)
                if rescue is not None and module.passes_rescue_gate(
                        rescue, config.rescue_min_ncc,
                        config.rescue_min_parallax_deg, config.rescue_min_views):
                    center = rescue
            if center is None:
                continue
            # depth_competition_offsets_m is empty -> unique_depth_winner True.
            accepted_points.append(point)
            accepted_colors.append(center["color"])
            accepted_meta.append([center["views"], center["parallax"],
                                  center["ncc"], center["candidate_views"]])
            accepted_meas.append({
                "clique_frames": center["clique_frames"],
                "clique_pixels": [np.asarray(p, float) for p in center["clique_pixels"]],
                "clique_colors": [np.asarray(c, float) for c in center["clique_colors"]],
            })
        mem_guard()
    xyz = np.asarray(accepted_points, float).reshape(-1, 3)
    rgb = np.asarray(accepted_colors, float).reshape(-1, 3)
    meta = np.asarray(accepted_meta, float).reshape(-1, 4)
    return xyz, rgb, meta, accepted_meas, image_cache.peak_bytes


# ---------------------------------------------------------------------------
# Median fusion (COLMAP StereoFusion adaptation).
# ---------------------------------------------------------------------------
def project_point(frame, X):
    cam = frame.R @ X + frame.t
    z = cam[2]
    homo = frame.K @ cam
    return homo[:2] / z, float(z)


def median_fusion(frames, xyz, meas, config_normal, fusion):
    N = len(xyz)
    normal = config_normal
    min_px = fusion["min_num_pixels"]
    max_reproj = fusion["max_reproj_error_px"]
    max_depth_rel = fusion["max_depth_error_rel"]
    cos_norm = math.cos(math.radians(fusion["max_normal_error_deg"]))
    radius = fusion["neighbor_radius_m"]

    frame_by_index = frames  # frames list; measurement stores frame_id -> need index
    # map frame_id -> position in frames list
    fid_to_idx = {int(f.frame_id): i for i, f in enumerate(frames)}

    # Precompute per-point measurements as (frame_idx, pixel(2), int_pixel(2), color(3)).
    pt_meas = []
    for i in range(N):
        m = meas[i]
        rows = []
        for fid, px, col in zip(m["clique_frames"], m["clique_pixels"], m["clique_colors"]):
            fidx = fid if isinstance(fid, (int, np.integer)) else fid_to_idx[int(fid)]
            rows.append((int(fidx), np.asarray(px, float),
                         (int(round(px[0])), int(round(px[1]))), np.asarray(col, float)))
        pt_meas.append(rows)

    # Spatial hash on the plane (X-Z) for neighbor candidate lookup during BFS.
    cell = radius
    grid = defaultdict(list)
    for i in range(N):
        key = (int(math.floor(xyz[i, 0] / cell)), int(math.floor(xyz[i, 2] / cell)))
        grid[key].append(i)

    def neighbors(i):
        cx = int(math.floor(xyz[i, 0] / cell))
        cz = int(math.floor(xyz[i, 2] / cell))
        out = []
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                out.extend(grid.get((cx + dx, cz + dz), ()))
        return out

    fused_mask = defaultdict(set)      # frame_idx -> set of consumed int pixels
    consumed_meas = set()              # (point_idx, frame_idx)
    # Per-point precompute camera-frame depth for its clique frames not needed globally;
    # compute on demand.

    out_xyz, out_rgb, out_meta = [], [], []
    cluster_sizes = []
    gate_rejects = {"reproj": 0, "depth": 0, "normal": 0, "pixel_locked": 0}
    grow_attach = 0

    for seed in range(N):
        # skip if seed has no free measurement left
        if all((seed, r[0]) in consumed_meas or r[2] in fused_mask[r[0]]
               for r in pt_meas[seed]):
            continue
        Xref = xyz[seed]
        cluster_X, cluster_col, cluster_norm = [], [], []
        cluster_meas_count = 0
        distinct_views = set()
        stack = [seed]
        seen = {seed}
        while stack:
            j = stack.pop()
            Xj = xyz[j]
            attached_here = False
            for (fidx, px, ipx, col) in pt_meas[j]:
                if (j, fidx) in consumed_meas:
                    continue
                if ipx in fused_mask[fidx]:
                    gate_rejects["pixel_locked"] += 1
                    continue
                frame = frames[fidx]
                proj, depth_j = project_point(frame, Xj)
                # reprojection gate: reference point must reproject near this
                # measurement's pixel in the same view.
                proj_ref, depth_ref = project_point(frame, Xref)
                if math.hypot(proj_ref[0] - px[0], proj_ref[1] - px[1]) > max_reproj:
                    gate_rejects["reproj"] += 1
                    continue
                # relative depth gate (camera-frame depth of Xj vs Xref).
                if abs(depth_j - depth_ref) / max(abs(depth_ref), 1e-6) > max_depth_rel:
                    gate_rejects["depth"] += 1
                    continue
                # normal gate (all measurements share the certified plane normal).
                if float(normal @ normal) < cos_norm:
                    gate_rejects["normal"] += 1
                    continue
                # accept measurement -> single-pixel lock.
                consumed_meas.add((j, fidx))
                fused_mask[fidx].add(ipx)
                cluster_X.append(Xj)
                cluster_col.append(col)
                cluster_norm.append(normal)
                cluster_meas_count += 1
                distinct_views.add(fidx)
                attached_here = True
            if attached_here:
                grow_attach += 1
            # region-grow: consider spatial neighbors whose reference reprojects
            # within the reproj gate in at least one shared view.
            for k in neighbors(j):
                if k in seen:
                    continue
                # cheap 3D proximity pre-check (2*radius on plane).
                if abs(xyz[k, 0] - Xref[0]) > radius or abs(xyz[k, 2] - Xref[2]) > radius:
                    continue
                seen.add(k)
                stack.append(k)
        if cluster_meas_count >= min_px:
            cx = np.median(np.stack(cluster_X), axis=0)
            ccol = np.median(np.stack(cluster_col), axis=0)
            cnorm = np.median(np.stack(cluster_norm), axis=0)
            out_xyz.append(cx)
            out_rgb.append(ccol)
            out_meta.append([cluster_meas_count, len(distinct_views)])
            cluster_sizes.append(cluster_meas_count)
        # else: measurements consumed (single-pixel lock) and discarded.
    return (np.asarray(out_xyz, float).reshape(-1, 3),
            np.asarray(out_rgb, float).reshape(-1, 3),
            np.asarray(out_meta, float).reshape(-1, 2),
            cluster_sizes, gate_rejects, grow_attach)


def write_fused_ply(path: Path, xyz, rgb, meta):
    with path.open("w", encoding="utf-8") as s:
        s.write("ply\nformat ascii 1.0\n")
        s.write(f"element vertex {len(xyz)}\n")
        s.write("property float x\nproperty float y\nproperty float z\n")
        s.write("property uchar red\nproperty uchar green\nproperty uchar blue\n")
        s.write("property float cluster_measurements\nproperty float distinct_views\nend_header\n")
        for p, c, m in zip(xyz, rgb, meta, strict=True):
            cu = np.clip(np.rint(c), 0, 255).astype(np.uint8)
            s.write(f"{p[0]:.7f} {p[1]:.7f} {p[2]:.7f} {cu[0]} {cu[1]} {cu[2]} "
                    f"{m[0]:.0f} {m[1]:.0f}\n")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    module = load_pinned_module()
    paths = default_inputs()
    planes = json.loads(paths["planes"].read_text())
    surfaces = module.select_surfaces(planes, [SURFACE_ID], False)
    floor = surfaces[0]
    config = module.SweepConfig(**CONFIG)
    frames = module.load_frames(paths["frame_meta"], paths["ledger"], paths["photos"])
    if len(frames) != 115:
        raise RuntimeError(f"expected 115 frames, got {len(frames)}")
    print(f"[{time.perf_counter()-t0:.1f}s] loaded {len(frames)} frames; sweeping...",
          flush=True)

    xyz, rgb, meta, meas, peak_img_bytes = sweep_traced(
        module, floor, planes["floor"], frames, config)
    gc.collect()
    print(f"[{time.perf_counter()-t0:.1f}s] swept {len(xyz)} accepted points; "
          f"RSS {rss_gb():.2f} GB", flush=True)

    # --- Fidelity: reproduce the frozen union PLY byte-for-byte. ---
    union_ply = OUT_DIR / "union_baseline.ply"
    module.write_ply(union_ply, xyz, rgb, meta)
    union_sha = sha256_file(union_ply)
    union_exact = (len(xyz) == EXPECTED_HISTORICAL_POINTS
                   and union_sha == EXPECTED_HISTORICAL_PLY_SHA256)
    if not union_exact:
        raise RuntimeError(
            f"union baseline diverged from pinned generator: points={len(xyz)}, "
            f"sha={union_sha} (expected {EXPECTED_HISTORICAL_PLY_SHA256})")
    print(f"[{time.perf_counter()-t0:.1f}s] union reproduced exact: "
          f"{len(xyz)} pts sha={union_sha[:12]}", flush=True)

    # --- Median fusion. ---
    normal = np.asarray(planes["floor"]["normal"], float)
    normal /= np.linalg.norm(normal)
    fx, frgb, fmeta, cluster_sizes, gate_rejects, grow_attach = median_fusion(
        frames, xyz, meas, normal, FUSION)
    gc.collect()
    fused_ply = OUT_DIR / "median_fusion.ply"
    write_fused_ply(fused_ply, fx, frgb, fmeta)
    fused_sha = sha256_file(fused_ply)
    print(f"[{time.perf_counter()-t0:.1f}s] fused {len(fx)} points sha={fused_sha[:12]}; "
          f"RSS {rss_gb():.2f} GB", flush=True)

    manifest = {
        "schema": "u3_median_fusion_prototype_v1",
        "capture": "cap50",
        "surface_id": SURFACE_ID,
        "generator_revision": PINNED_REVISION,
        "generator_source_sha256": PINNED_SOURCE_SHA256,
        "config_sweep": {k: (list(v) if isinstance(v, tuple) else v)
                         for k, v in CONFIG.items()},
        "config_fusion": FUSION,
        "union": {
            "ply": str(union_ply), "ply_sha256": union_sha,
            "points": int(len(xyz)), "reproduced_frozen_exact": union_exact,
            "expected_ply_sha256": EXPECTED_HISTORICAL_PLY_SHA256,
        },
        "median_fusion": {
            "ply": str(fused_ply), "ply_sha256": fused_sha,
            "points": int(len(fx)),
            "reduction_frac": 1.0 - len(fx) / len(xyz),
            "cluster_size_min": int(min(cluster_sizes)) if cluster_sizes else 0,
            "cluster_size_median": float(np.median(cluster_sizes)) if cluster_sizes else 0.0,
            "cluster_size_max": int(max(cluster_sizes)) if cluster_sizes else 0,
            "clusters_emitted": int(len(fx)),
            "gate_rejects": gate_rejects,
            "grow_attach_events": int(grow_attach),
        },
        "elapsed_s": time.perf_counter() - t0,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "peak_loaded_image_bytes": int(peak_img_bytes),
    }
    (OUT_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
