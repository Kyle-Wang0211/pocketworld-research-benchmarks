#!/usr/bin/env python3.11
"""E13 step1 — full observation table + exact-site family inventory (read-only).

Per cap (off baseline run):
  * observation table: every 3D point -> [(image_id, kp_idx, x, y, site_uid)]
    with 100% coverage (verified in step0).
  * site identity: bit-identical (x,y) inside one frame (DSP-SIFT variant alias,
    same definition as E9 RECON exact_site_grid).
  * multi-occupancy sites: sites whose variants are observed by >=2 distinct 3D
    points -> competition evidence. Families = connected components of points
    linked by shared sites.
  * Delta-fh statistics inside families (production plane, no re-anchor):
    cross-layer (true-floor vs ghost-band pairing) vs same-layer.
Outputs analysis/step1_inventory_<cap>.json + npz caches for step2.
"""
import json
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E13_dual_birth_inventory/scripts")
from e13_lib import (E13, OFF_RUN, load_plane, read_images_bin_full,
                     read_points3d_bin_full)


class DSU:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def main(cap):
    run = OFF_RUN[cap]
    ids, xyz, rgb, err, tracks = read_points3d_bin_full(f"{run}/points3D.bin")
    images = read_images_bin_full(f"{run}/images.bin")
    pn, pd = load_plane(cap)
    fh = xyz @ pn + pd
    npts = len(ids)

    # --- site ids per frame: bit-identical xy (float64 bits, = float32 db bits, step0 verified)
    site_of = {}  # image_id -> array kp_idx -> local site idx
    n_sites_frame = {}
    for iid, im in images.items():
        v = im["xys"].view(np.uint64)  # (N,2) bit patterns
        key = (v[:, 0] << np.uint64(1)) ^ v[:, 1]  # cheap combine; exactness via unique on structured
        # exact: use structured void view for uniqueness
        sv = np.ascontiguousarray(im["xys"]).view([("", np.uint64), ("", np.uint64)]).ravel()
        _, inv = np.unique(sv, return_inverse=True)
        site_of[iid] = inv.reshape(-1).astype(np.int64)
        n_sites_frame[iid] = int(inv.max()) + 1 if len(inv) else 0

    # --- observation table (flat arrays)
    obs_pt = np.empty(sum(len(t) for t in tracks), np.int64)
    obs_iid = np.empty_like(obs_pt)
    obs_kp = np.empty_like(obs_pt)
    o = 0
    for i, tr in enumerate(tracks):
        n = len(tr)
        obs_pt[o:o+n] = i
        obs_iid[o:o+n] = tr[:, 0]
        obs_kp[o:o+n] = tr[:, 1]
        o += n
    # site uid = iid * 2^24 + local site (kp counts are 8192 << 2^24)
    loc = np.empty(len(obs_pt), np.int64)
    for iid in images:
        m = obs_iid == iid
        loc[m] = site_of[iid][obs_kp[m]]
    obs_site = obs_iid * (1 << 24) + loc

    # --- multi-occupancy sites
    order = np.argsort(obs_site, kind="stable")
    s_sorted = obs_site[order]
    p_sorted = obs_pt[order]
    bounds = np.flatnonzero(np.diff(s_sorted)) + 1
    groups = np.split(np.arange(len(s_sorted)), bounds)
    dsu = DSU(npts)
    shared_sites = 0
    shared_sites_pts = []
    same_site_same_point = 0  # site occupied twice by SAME point (multi-variant in one track)
    for g in groups:
        pts = np.unique(p_sorted[g])
        if len(g) > len(pts):
            same_site_same_point += 1
        if len(pts) >= 2:
            shared_sites += 1
            shared_sites_pts.append(pts)
            for q in pts[1:]:
                dsu.union(int(pts[0]), int(q))

    # --- families
    root = np.array([dsu.find(i) for i in range(npts)])
    fam_of = {}
    fams = defaultdict(list)
    for i in range(npts):
        fams[root[i]].append(i)
    families = [np.array(v) for v in fams.values() if len(v) >= 2]
    fam_sizes = np.array([len(f) for f in families])

    # --- Delta-fh stats inside families (pairwise within shared sites for locality)
    TRUE_LO, TRUE_HI = -0.0075, 0.0125
    GHOST_LO, GHOST_HI = -0.045, -0.020
    dfh_all = []
    cross_layer_sites = 0
    same_layer_sites = 0
    for pts in shared_sites_pts:
        f = fh[pts]
        dfh = float(f.max() - f.min())
        dfh_all.append(dfh)
        has_true = np.any((f >= TRUE_LO) & (f < TRUE_HI))
        has_ghost = np.any((f >= GHOST_LO) & (f < GHOST_HI))
        if has_true and has_ghost:
            cross_layer_sites += 1
        elif dfh < 0.015:
            same_layer_sites += 1
    dfh_all = np.array(dfh_all)

    fam_cross = 0
    fam_true_ghost = []
    for fi, pts in enumerate(families):
        f = fh[pts]
        has_true = np.any((f >= TRUE_LO) & (f < TRUE_HI))
        has_ghost = np.any((f >= GHOST_LO) & (f < GHOST_HI))
        if has_true and has_ghost:
            fam_cross += 1
            fam_true_ghost.append(fi)

    in_fam = np.zeros(npts, bool)
    for pts in families:
        in_fam[pts] = True
    ghost_mask = (fh >= GHOST_LO) & (fh < GHOST_HI)
    true_mask = (fh >= TRUE_LO) & (fh < TRUE_HI)
    fat_mask = (fh >= -0.045) & (fh < -0.010)

    stats = {
        "cap": cap, "run": run, "n_points": int(npts),
        "n_obs": int(len(obs_pt)),
        "sites_touched_by_tracks": int(len(groups)),
        "sites_shared_by_2plus_points": int(shared_sites),
        "sites_multi_variant_same_point": int(same_site_same_point),
        "n_families_ge2": int(len(families)),
        "family_size_hist": {str(k): int((fam_sizes == k).sum()) for k in range(2, 9)},
        "family_size_max": int(fam_sizes.max()) if len(fam_sizes) else 0,
        "points_in_families": int(in_fam.sum()),
        "points_in_families_pct": round(100 * float(in_fam.mean()), 2),
        "shared_site_dfh_mm": {
            "p50": round(float(np.median(dfh_all)) * 1000, 2) if len(dfh_all) else None,
            "p90": round(float(np.percentile(dfh_all, 90)) * 1000, 2) if len(dfh_all) else None,
            "hist_mm": {f"{a}-{b}": int(((dfh_all >= a/1000) & (dfh_all < b/1000)).sum())
                        for a, b in [(0, 2), (2, 5), (5, 15), (15, 25), (25, 50), (50, 100), (100, 100000)]},
        },
        "cross_layer_shared_sites(true+ghost)": int(cross_layer_sites),
        "same_layer_shared_sites(dfh<15mm)": int(same_layer_sites),
        "families_with_true_and_ghost": int(fam_cross),
        "band_membership_of_family_points": {
            "ghost_band_pts_total": int(ghost_mask.sum()),
            "ghost_band_pts_in_families": int((ghost_mask & in_fam).sum()),
            "ghost_band_in_family_pct": round(100 * float((ghost_mask & in_fam).sum() / max(ghost_mask.sum(), 1)), 2),
            "mid_fat_pts_total": int(fat_mask.sum()),
            "mid_fat_pts_in_families": int((fat_mask & in_fam).sum()),
            "true_floor_pts_total": int(true_mask.sum()),
            "true_floor_pts_in_families": int((true_mask & in_fam).sum()),
        },
    }
    print(json.dumps(stats, indent=1))
    json.dump(stats, open(f"{E13}/analysis/step1_inventory_{cap}.json", "w"), indent=1)

    # cache for step2 (flat obs table + site ids + families)
    np.savez_compressed(
        f"{E13}/analysis/step1_cache_{cap}.npz",
        ids=ids, xyz=xyz, rgb=rgb, err=err, fh=fh,
        obs_pt=obs_pt, obs_iid=obs_iid, obs_kp=obs_kp, obs_site=obs_site,
        family_root=root,
    )
    print(f"[{cap}] cache saved")


if __name__ == "__main__":
    for cap in ("cap51", "cap50"):
        main(cap)
