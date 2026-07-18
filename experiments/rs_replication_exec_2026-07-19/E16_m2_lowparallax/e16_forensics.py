#!/usr/bin/env python3.11
"""E16 forensics — warp-immune attribution + frame shape checks.

1. ABSENT-point attribution (per-face, warp-immune): the diff-red points live
   in the OFF cloud, measured in the OFF cloud's own fixed frames (production
   plane + off_r2 wall frame). Whatever the arm's gauge did, this ledger says
   WHICH surfaces lost the geometry the arm no longer reproduces:
   floor slab / true-floor band / ghost band / dominant-wall slab / objects.
2. NEW-point count (arm points with no OFF neighbor within 2cm) for symmetry.
3. RAW-frame 5mm histograms (off vs biting arms) — shape check, E12 lesson:
   never quote band numbers when the peak structure itself moved.
4. off x3 spread for the raw rulers (noise band for the zero-bite arms).
"""
import json, os
import numpy as np
from scipy.spatial import cKDTree

D = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{D}/experiments/rs_replication_exec_2026-07-19"
E9_RUNS = f"{EXP}/E9_birth_alias/runs"
E16 = f"{EXP}/E16_m2_lowparallax"
E16_RUNS, OUT = f"{E16}/runs", f"{E16}/analysis"

FLOOR_SLAB, WALL_MIN_FH, WALL_SLAB = 0.06, 0.10, 0.06
DIFF_ABSENT_M = 0.02


def read_ply(path):
    with open(path, "rb") as f:
        h = b""
        while not h.endswith(b"end_header\n"):
            h += f.readline()
        n = int([l for l in h.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        d = np.fromfile(f, dtype=rec, count=n)
    return np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)


def anchor_floor(fh):
    hist, edges = np.histogram(fh[np.abs(fh) <= 0.12], bins=np.arange(-0.12, 0.1205, 0.005))
    k = int(np.argmax(hist))
    thr = 0.35 * hist[k]
    lo = k
    while lo > 0 and hist[lo-1] >= thr: lo -= 1
    hi = k
    while hi < len(hist)-1 and hist[hi+1] >= thr: hi += 1
    centers = 0.5*(edges[lo:hi+1] + edges[lo+1:hi+2])
    w = hist[lo:hi+1].astype(float)
    return float((centers*w).sum()/w.sum())


def fit_dominant_wall(xyz, fh, pn):
    P = xyz[fh > 0.30]
    if len(P) < 500: return None, None
    best = (None, None, -1)
    for ang in np.arange(0, 180, 1.0):
        t = np.radians(ang)
        d3 = np.array([np.cos(t), 0.0, np.sin(t)])
        d3 = d3 - (d3 @ pn)*pn
        nl = np.linalg.norm(d3)
        if nl < 1e-6: continue
        d3 /= nl
        pr = P @ d3
        hist, edges = np.histogram(pr, bins=np.arange(pr.min(), pr.max()+0.01, 0.01))
        k = int(np.argmax(hist))
        if hist[k] > best[2]: best = (d3, 0.5*(edges[k]+edges[k+1]), int(hist[k]))
    return best[0], best[1]


def face_split(xyz, fh, wd, wo):
    floor_m = np.abs(fh) <= FLOOR_SLAB
    sd = xyz @ wd - wo
    wall_m = (np.abs(sd) <= WALL_SLAB) & (fh > WALL_MIN_FH)
    obj_m = ~floor_m & ~wall_m
    return floor_m, wall_m, obj_m


def main():
    res = {}
    for cap in ("cap50", "cap51"):
        gm = json.load(open(f"{D}/data/pocketworld_captures/{cap}/device_full_pull_2026-07-17/ghost_mask.json"))
        pn, pd = np.array(gm["plane_n"], float), float(gm["plane_d"])
        off_xyz, _ = read_ply(f"{E9_RUNS}/{cap}_off_r2/replay_finalize.ply")
        fh_raw = off_xyz @ pn + pd
        shift = anchor_floor(fh_raw)
        fh = fh_raw - shift
        wd, wo = fit_dominant_wall(off_xyz, fh, pn)
        floor_m, wall_m, obj_m = face_split(off_xyz, fh, wd, wo)
        true_m = (fh >= -0.015) & (fh <= FLOOR_SLAB)
        ghost_m = (fh >= -0.045) & (fh < -0.020)
        off_tot = {"floor_slab": int(floor_m.sum()), "true_floor": int(true_m.sum()),
                   "ghost_band": int(ghost_m.sum()), "wall_slab": int(wall_m.sum()),
                   "objects": int(obj_m.sum()), "all": len(off_xyz)}
        res[cap] = {"off_r2_face_totals": off_tot, "arms": {}}
        arms = [a for a in ("m2", "m2_r002", "m2_r005", "m2_r015")
                if os.path.isdir(f"{E16_RUNS}/{cap}_{a}")]
        for arm in arms:
            arm_xyz, _ = read_ply(f"{E16_RUNS}/{cap}_{arm}/replay_finalize.ply")
            d_off2arm, _ = cKDTree(arm_xyz).query(off_xyz, k=1)
            absent = d_off2arm > DIFF_ABSENT_M
            d_arm2off, _ = cKDTree(off_xyz).query(arm_xyz, k=1)
            new = d_arm2off > DIFF_ABSENT_M
            a = {"absent_total": int(absent.sum()),
                 "absent_pct_of_off": round(100*float(absent.mean()), 2),
                 "new_in_arm_total": int(new.sum()),
                 "new_in_arm_pct": round(100*float(new.mean()), 2),
                 "absent_by_face": {
                     "floor_slab": int((absent & floor_m).sum()),
                     "true_floor": int((absent & true_m).sum()),
                     "ghost_band": int((absent & ghost_m).sum()),
                     "wall_slab": int((absent & wall_m).sum()),
                     "objects": int((absent & obj_m).sum())},
                 "absent_face_pct_of_face": {
                     "floor_slab": round(100*float((absent & floor_m).sum())/max(off_tot["floor_slab"],1), 2),
                     "true_floor": round(100*float((absent & true_m).sum())/max(off_tot["true_floor"],1), 2),
                     "ghost_band": round(100*float((absent & ghost_m).sum())/max(off_tot["ghost_band"],1), 2),
                     "wall_slab": round(100*float((absent & wall_m).sum())/max(off_tot["wall_slab"],1), 2),
                     "objects": round(100*float((absent & obj_m).sum())/max(off_tot["objects"],1), 2)}}
            res[cap]["arms"][arm] = a
            print(f"[{cap}/{arm}] absent={a['absent_total']} ({a['absent_pct_of_off']}%) new={a['new_in_arm_total']} "
                  f"| absent per face floor={a['absent_face_pct_of_face']['floor_slab']}% true={a['absent_face_pct_of_face']['true_floor']}% "
                  f"ghost={a['absent_face_pct_of_face']['ghost_band']}% wall={a['absent_face_pct_of_face']['wall_slab']}% obj={a['absent_face_pct_of_face']['objects']}%")

        # raw 5mm histograms (shape check)
        hists = {}
        def hist_of(path):
            x, _ = read_ply(path)
            fr = x @ pn + pd
            h, _ = np.histogram(fr[np.abs(fr) <= 0.10], bins=np.arange(-0.10, 0.1005, 0.005))
            return h.tolist()
        hists["off_r2"] = hist_of(f"{E9_RUNS}/{cap}_off_r2/replay_finalize.ply")
        for arm in arms:
            hists[arm] = hist_of(f"{E16_RUNS}/{cap}_{arm}/replay_finalize.ply")
        res[cap]["raw_hist_5mm_[-100,100)mm"] = hists

        # off x3 spread for raw rulers (noise band)
        spread = {}
        for r in ("off_r1", "off_r2", "off_r3"):
            x, _ = read_ply(f"{E9_RUNS}/{cap}_{r}/replay_finalize.ply")
            fr = x @ pn + pd
            spread[r] = {"floor_peak": int(((fr >= -0.0075) & (fr < 0.0125)).sum()),
                         "ghost_band": int(((fr >= -0.045) & (fr < -0.020)).sum()),
                         "below_floor": int((fr < -0.10).sum())}
        res[cap]["off_raw_spread"] = spread
        print(f"[{cap}] off raw spread: {spread}")

    json.dump(res, open(f"{OUT}/e16_forensics.json", "w"), indent=1)
    print("saved", f"{OUT}/e16_forensics.json")


if __name__ == "__main__":
    main()
