#!/usr/bin/env python3
"""E21 create-gate scan rulers: per-arm n/streamed/ghost/bimodality/thickness/
cover/2v%/wall, device fixed plane + anchor_floor/bimodality verbatim from
f_rulers lineage."""
import json, os, re, struct
import numpy as np

EXP = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19"
DATA = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures"
E21 = f"{EXP}/E21_create_gate"
GHOST_BAND = (-0.045, -0.020)

def read_p3d(p):
    xyz, tl = [], []
    with open(p, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            f.read(8)
            xyz.append(struct.unpack("<3d", f.read(24)))
            f.read(3 + 8)
            t = struct.unpack("<Q", f.read(8))[0]
            f.read(t * 8)
            tl.append(t)
    return np.asarray(xyz), np.asarray(tl)

def anchor_floor(fh):
    hist, edges = np.histogram(fh[np.abs(fh) <= 0.12], bins=np.arange(-0.12, 0.1205, 0.005))
    k = int(np.argmax(hist)); thr = 0.35 * hist[k]
    lo = k
    while lo > 0 and hist[lo-1] >= thr: lo -= 1
    hi = k
    while hi < len(hist)-1 and hist[hi+1] >= thr: hi += 1
    centers = 0.5*(edges[lo:hi+1] + edges[lo+1:hi+2]); w = hist[lo:hi+1].astype(float)
    return float((centers*w).sum()/w.sum())

def bimodality(fh):
    hist, edges = np.histogram(fh, bins=np.arange(-0.06, 0.0205, 0.005))
    centers = (0.5*(edges[:-1]+edges[1:]) * 1000).round(1)
    k_main = int(np.argmax(hist))
    ghost_win = centers < -15
    k_ghost = int(np.argmax(np.where(ghost_win, hist, -1)))
    return round(float(hist[k_ghost]) / max(int(hist[k_main]), 1), 3)

def floor_metrics(xyz, fh):
    slab = np.abs(fh) <= 0.06
    Q = xyz[slab]
    key = np.floor(Q[:, [0, 2]] / 0.05).astype(np.int64)
    kk = key[:, 0] * 1000003 + key[:, 1]
    order = np.argsort(kk); kk, vv = kk[order], fh[slab][order]
    sp = []; i = 0
    while i < len(kk):
        j = i
        while j < len(kk) and kk[j] == kk[i]: j += 1
        if j - i >= 8: sp.append(np.percentile(vv[i:j], 90) - np.percentile(vv[i:j], 10))
        i = j
    cov = len(set(map(tuple, np.floor(Q[:, [0, 2]] / 0.02).astype(np.int64))))
    return (float(np.median(sp)) if sp else None), cov

report = {}
for cap in ("cap51", "cap50"):
    gm = json.load(open(f"{DATA}/{cap}/device_full_pull_2026-07-17/ghost_mask.json"))
    pn, pd = np.array(gm["plane_n"], float), float(gm["plane_d"])
    rows = {}
    # fixed ruler: anchor computed ONCE from the g10 baseline cloud, applied to
    # every arm (per-arm self-anchor jumps modes when an arm guts the floor).
    xyz10, _ = read_p3d(f"{E21}/runs/{cap}_g10/points3D.bin")
    shift10 = anchor_floor(xyz10 @ pn + pd)
    print(f"===== {cap} (fixed anchor from g10: {shift10*1000:.1f}mm) =====")
    for g in (2, 4, 6, 8, 10):
        d = f"{E21}/runs/{cap}_g{g}"
        if not os.path.exists(f"{d}/points3D.bin"):
            print(f"g{g}: MISSING"); continue
        res = open(f"{d}/run.log").read()
        m = re.search(r"RESULT.*n_points=(\d+).*track3plus=(\d+).*stream_ms=([0-9.]+).*finalize_ms=([0-9.]+)", res)
        xyz, tl = read_p3d(f"{d}/points3D.bin")
        fh = xyz @ pn + pd
        fh -= shift10
        thick, cov = floor_metrics(xyz, fh)
        rows[f"g{g}"] = r = {
            "n": len(xyz), "2v_pct": round(float((tl == 2).mean()) * 100, 2),
            "ghost_2045": int(((fh >= GHOST_BAND[0]) & (fh < GHOST_BAND[1])).sum()),
            "peakratio": bimodality(fh),
            "thickness": round(thick, 5) if thick else None, "cover_2cm": cov,
            "stream_s": round(float(m.group(3))/1000, 1) if m else None,
            "finalize_s": round(float(m.group(4))/1000, 1) if m else None,
        }
        print(f"g{g}: n={r['n']} 2v%={r['2v_pct']} ghost={r['ghost_2045']} peak={r['peakratio']} "
              f"thick={r['thickness']} cover={r['cover_2cm']} stream={r['stream_s']}s fin={r['finalize_s']}s")
    report[cap] = rows
json.dump(report, open(f"{E21}/scan_rulers.json", "w"), indent=1)
print("WROTE", f"{E21}/scan_rulers.json")
