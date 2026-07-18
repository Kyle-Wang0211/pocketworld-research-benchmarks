#!/usr/bin/env python3.11
"""E13 step2 — cross-layer pixel-domain diagnosis (read-only).

Question to nail down: do ghost-band points and true-floor points share pixel
evidence AT ALL, and at what pixel radius would a site-identity link appear?

Per cap:
  A. For every ghost-band point observation, nearest same-frame true-floor
     observation distance (px). Per-point min across its observations.
  B. Quantized-site sensitivity: site = (frame, floor(x/q), floor(y/q)) for
     q in {exact, 0.5, 1, 2, 4, 8 px}: how many ghost points get linked to a
     true-floor point through a shared quantized site.
  C. Frame overlap: ghost point tracks vs true-floor tracks (same frame at all).
Outputs analysis/step2_crosslayer_<cap>.json
"""
import json
import sys
from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E13_dual_birth_inventory/scripts")
from e13_lib import E13, OFF_RUN, read_images_bin_full

TRUE_LO, TRUE_HI = -0.0075, 0.0125
GHOST_LO, GHOST_HI = -0.045, -0.020


def main(cap):
    z = np.load(f"{E13}/analysis/step1_cache_{cap}.npz")
    fh = z["fh"]
    obs_pt, obs_iid, obs_kp = z["obs_pt"], z["obs_iid"], z["obs_kp"]
    images = read_images_bin_full(f"{OFF_RUN[cap]}/images.bin")

    ghost_pts = np.flatnonzero((fh >= GHOST_LO) & (fh < GHOST_HI))
    true_pts = np.flatnonzero((fh >= TRUE_LO) & (fh < TRUE_HI))
    ghost_set = set(ghost_pts.tolist())
    true_set = set(true_pts.tolist())

    # observation xy lookup
    def xy_of(iid, kp):
        return images[iid]["xys"][kp]

    is_ghost_obs = np.isin(obs_pt, ghost_pts)
    is_true_obs = np.isin(obs_pt, true_pts)

    # --- A: per-frame KDTree over true-floor observations
    frames = np.unique(obs_iid)
    true_by_frame = {}
    for iid in frames:
        m = is_true_obs & (obs_iid == iid)
        if m.sum():
            xy = images[iid]["xys"][obs_kp[m]]
            true_by_frame[iid] = (cKDTree(xy), obs_pt[m])
    dmin_per_ghost = defaultdict(lambda: np.inf)
    n_ghost_obs_with_true_in_frame = 0
    n_ghost_obs_total = 0
    gm = np.flatnonzero(is_ghost_obs)
    for o in gm:
        iid = obs_iid[o]
        n_ghost_obs_total += 1
        t = true_by_frame.get(iid)
        if t is None:
            continue
        n_ghost_obs_with_true_in_frame += 1
        d, _ = t[0].query(xy_of(iid, obs_kp[o]), k=1)
        p = obs_pt[o]
        if d < dmin_per_ghost[p]:
            dmin_per_ghost[p] = d
    dmin = np.array([dmin_per_ghost[p] for p in ghost_pts if np.isfinite(dmin_per_ghost[p])])
    n_no_frame_overlap = int(len(ghost_pts) - len(dmin))

    hist_edges = [0, 0.5, 1, 2, 4, 8, 16, 32, 1e9]
    hist = {f"{hist_edges[i]}-{hist_edges[i+1]}px": int(((dmin >= hist_edges[i]) & (dmin < hist_edges[i+1])).sum())
            for i in range(len(hist_edges) - 1)}

    # --- B: quantized-site sensitivity
    sens = {}
    for q in ("exact", 0.5, 1.0, 2.0, 4.0, 8.0):
        linked_ghost = set()
        site_map = defaultdict(lambda: [False, False, set()])  # has_true, has_ghost, ghost pts
        for o in np.flatnonzero(is_ghost_obs | is_true_obs):
            iid = obs_iid[o]
            xy = xy_of(iid, obs_kp[o])
            if q == "exact":
                key = (int(iid), float(xy[0]).hex(), float(xy[1]).hex())
            else:
                key = (int(iid), int(np.floor(xy[0] / q)), int(np.floor(xy[1] / q)))
            ent = site_map[key]
            p = int(obs_pt[o])
            if p in true_set:
                ent[0] = True
            else:
                ent[1] = True
                ent[2].add(p)
        for ent in site_map.values():
            if ent[0] and ent[1]:
                linked_ghost |= ent[2]
        sens[str(q)] = {"ghost_pts_linked_to_true": len(linked_ghost),
                        "pct_of_ghost_band": round(100 * len(linked_ghost) / max(len(ghost_pts), 1), 2)}

    out = {
        "cap": cap,
        "n_ghost_band_pts": int(len(ghost_pts)),
        "n_true_floor_pts": int(len(true_pts)),
        "ghost_obs_total": int(n_ghost_obs_total),
        "ghost_obs_sharing_frame_with_any_true_obs_pct": round(100 * n_ghost_obs_with_true_in_frame / max(n_ghost_obs_total, 1), 2),
        "ghost_pts_with_no_true_obs_in_any_of_their_frames": n_no_frame_overlap,
        "nearest_true_obs_px_per_ghost_pt": {
            "p50": round(float(np.median(dmin)), 2) if len(dmin) else None,
            "p90": round(float(np.percentile(dmin, 90)), 2) if len(dmin) else None,
            "hist": hist,
        },
        "quantized_site_link_sensitivity": sens,
    }
    print(json.dumps(out, indent=1))
    json.dump(out, open(f"{E13}/analysis/step2_crosslayer_{cap}.json", "w"), indent=1)


if __name__ == "__main__":
    for cap in ("cap51", "cap50"):
        main(cap)
