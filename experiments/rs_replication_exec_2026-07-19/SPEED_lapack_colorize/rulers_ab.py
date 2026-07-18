#!/usr/bin/env python3
"""LAPACK A/B rulers: per-run n/ghost/thickness/cover (device fixed plane +
anchor_floor verbatim from f_rulers) + finalize wall + dense_backend readback.
Asserts every L run actually used LAPACK and every E run EIGEN."""
import json, os, re, struct
import numpy as np

EXP = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19"
DATA = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures"
S = f"{EXP}/SPEED_lapack_colorize"
GHOST_BAND = (-0.045, -0.020)
CELL = 0.05
CELL_COVER = 0.02

def read_p3d(p):
    xyz = []
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            f.read(8)
            xyz.append(struct.unpack("<3d", f.read(24)))
            f.read(3 + 8)
            tl = struct.unpack("<Q", f.read(8))[0]
            f.read(tl * 8)
    return np.asarray(xyz)

def anchor_floor(fh):
    hist, edges = np.histogram(fh[np.abs(fh) <= 0.12], bins=np.arange(-0.12, 0.1205, 0.005))
    k = int(np.argmax(hist)); thr = 0.35 * hist[k]
    lo = k
    while lo > 0 and hist[lo-1] >= thr: lo -= 1
    hi = k
    while hi < len(hist)-1 and hist[hi+1] >= thr: hi += 1
    centers = 0.5*(edges[lo:hi+1] + edges[lo+1:hi+2]); w = hist[lo:hi+1].astype(float)
    return float((centers*w).sum()/w.sum())

def floor_metrics(xyz, fh):
    slab = np.abs(fh) <= 0.06
    Q = xyz[slab]
    key = np.floor(Q[:, [0, 2]] / CELL).astype(np.int64)
    kk = key[:, 0] * 1000003 + key[:, 1]
    order = np.argsort(kk)
    kk, vv = kk[order], fh[slab][order]
    sp = []
    i = 0
    while i < len(kk):
        j = i
        while j < len(kk) and kk[j] == kk[i]: j += 1
        if j - i >= 8:
            sp.append(np.percentile(vv[i:j], 90) - np.percentile(vv[i:j], 10))
        i = j
    cov = len(set(map(tuple, np.floor(Q[:, [0, 2]] / CELL_COVER).astype(np.int64))))
    return (float(np.median(sp)) if sp else None), cov

report = {}
for cap in ("cap51", "cap50"):
    gm = json.load(open(f"{DATA}/{cap}/device_full_pull_2026-07-17/ghost_mask.json"))
    pn, pd = np.array(gm["plane_n"], float), float(gm["plane_d"])
    rows = {}
    for arm in ("E", "L"):
        for r in (1, 2, 3):
            d = f"{S}/runs/{cap}_{arm}_r{r}"
            seg = json.load(open(f"{d}/finalize_segments.json"))
            backend = seg["dense_backend"]
            expect = "LAPACK" if arm == "L" else "EIGEN"
            assert backend == expect, f"{cap}_{arm}_r{r}: backend {backend} != {expect}"
            res = open(f"{d}/run.log").read()
            fin = float(re.search(r"finalize_ms=([0-9.]+)", res).group(1))
            xyz = read_p3d(f"{d}/points3D.bin")
            fh = xyz @ pn + pd
            fh -= anchor_floor(fh)
            thick, cov = floor_metrics(xyz, fh)
            rows[f"{arm}_r{r}"] = {
                "n": len(xyz),
                "ghost_2045": int(((fh >= GHOST_BAND[0]) & (fh < GHOST_BAND[1])).sum()),
                "thickness": round(thick, 5) if thick else None,
                "cover_2cm": cov,
                "finalize_s": round(fin / 1000, 1),
                "stage2_ms": seg["stage2_ms"],
                "dense_backend": backend,
            }
    report[cap] = rows
    print(f"===== {cap} =====")
    for k, v in rows.items():
        print(f"{k}: n={v['n']} ghost={v['ghost_2045']} thick={v['thickness']} "
              f"cover={v['cover_2cm']} fin={v['finalize_s']}s stage2={v['stage2_ms']}ms [{v['dense_backend']}]")
json.dump(report, open(f"{S}/ab_rulers.json", "w"), indent=1)
print("WROTE", f"{S}/ab_rulers.json")
