#!/usr/bin/env python3
# E19-B step ③ mechanism attribution:
#  - track-length distribution + 2-view share (before = E9 off runs, after = densified control)
#  - who do the npz "rescue" pairs connect to in the replay reconstruction?
#    (same track / two different tracks / one side / unborn)
#  - ghost band [-45,-20)mm x track-length cross-tab (certified fixed plane + shift-only anchor)
#  - parent-pair tri-ratio estimate vs colmap Retriangulate re_min_ratio
#  - counterfactual graph growth if the 48k/28k pairs HAD been new edges
import json, os, sqlite3, struct
import numpy as np

MAX_IMAGE_ID = 2147483647
D = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{D}/experiments/rs_replication_exec_2026-07-19"
E9RUNS = f"{EXP}/E9_birth_alias/runs"
OUT = f"{EXP}/E19_no_birth/B_match_enrichment"
GHOST_BAND = (-0.045, -0.02)

CFG = {
    "cap50": {"npz": f"{EXP}/E6_rescue_inject/cap50/rescue_provenance_cap50.npz",
              "db": f"{D}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_live.db",
              "gm": f"{D}/data/pocketworld_captures/cap50/device_full_pull_2026-07-17/ghost_mask.json",
              "off": ["cap50_off_r1", "cap50_off_r2", "cap50_off_r3"],
              "densified": f"{OUT}/runs/cap50_densified"},
    "cap51": {"npz": f"{EXP}/E6_rescue_inject/cap51/rescue_provenance_cap51.npz",
              "db": f"{D}/data/pocketworld_captures/cap51/replay_database/sfm_live.db",
              "gm": f"{D}/data/pocketworld_captures/cap51/device_full_pull_2026-07-17/ghost_mask.json",
              "off": ["cap51_off_r1", "cap51_off_r2", "cap51_off_r3"],
              "densified": f"{OUT}/runs/cap51_densified"},
}

def read_points3d(path):
    pts = {}
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            pid = struct.unpack("<Q", f.read(8))[0]
            xyz = struct.unpack("<3d", f.read(24))
            rgb = struct.unpack("<3B", f.read(3))
            struct.unpack("<d", f.read(8))  # error
            tl = struct.unpack("<Q", f.read(8))[0]
            track = np.frombuffer(f.read(8 * tl), dtype=np.uint32).reshape(tl, 2)
            pts[pid] = (np.array(xyz), track, rgb)
    return pts

def anchor_floor(fh):
    hist, edges = np.histogram(fh[np.abs(fh) <= 0.12], bins=np.arange(-0.12, 0.1205, 0.005))
    k = int(np.argmax(hist)); thr = 0.35 * hist[k]
    lo = k
    while lo > 0 and hist[lo-1] >= thr: lo -= 1
    hi = k
    while hi < len(hist)-1 and hist[hi+1] >= thr: hi += 1
    centers = 0.5*(edges[lo:hi+1] + edges[lo+1:hi+2]); w = hist[lo:hi+1].astype(float)
    return float((centers*w).sum()/w.sum())

def track_stats(pts):
    tl = np.array([len(t) for _, t, _ in pts.values()])
    hist = {str(k): int((tl == k).sum()) for k in range(2, 11)}
    hist["11+"] = int((tl >= 11).sum())
    return {"n_points": int(len(tl)), "two_view": int((tl == 2).sum()),
            "two_view_share_pct": round(100 * float((tl == 2).mean()), 2),
            "mean_track_len": round(float(tl.mean()), 3), "hist": hist}

def run_dir_stats(run_dir, pn, pd):
    pts = read_points3d(os.path.join(run_dir, "points3D.bin"))
    st = track_stats(pts)
    xyz = np.array([p for p, _, _ in pts.values()])
    tl = np.array([len(t) for _, t, _ in pts.values()])
    shift = anchor_floor(xyz @ pn + pd)
    fh = xyz @ pn + pd - shift
    g = (fh >= GHOST_BAND[0]) & (fh < GHOST_BAND[1])
    st.update({
        "gauge_shift_mm": round(shift * 1000, 1),
        "ghost_2045": int(g.sum()),
        "ghost_2045_two_view": int((g & (tl == 2)).sum()),
        "ghost_2045_3plus": int((g & (tl >= 3)).sum()),
        "ghost_two_view_share_pct": round(100 * float((tl[g] == 2).mean()), 2) if g.any() else None,
    })
    return st, pts, shift

def main():
    report = {}
    for cap, cfg in CFG.items():
        gm = json.load(open(cfg["gm"]))
        pn, pd = np.array(gm["plane_n"], float), float(gm["plane_d"])
        z = np.load(cfg["npz"], allow_pickle=True)
        f1, f2 = z["f1"], z["f2"]
        xy1, xy2 = z["xy1"].astype(np.float32), z["xy2"].astype(np.float32)
        pos, fl_h, dprod = z["pos"], z["floor_h"], z["dist_prod"]
        n = len(f1)

        db = sqlite3.connect(f"file:{cfg['db']}?mode=ro", uri=True)
        c = db.cursor()
        kp = {}
        for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
            kp[iid] = (np.frombuffer(data, np.float32).reshape(r, cols)[:, :2]
                       if r else np.zeros((0, 2), np.float32))
        tvg = {}
        total_tvg_corrs = 0
        for pid_, r, cols, data in c.execute("SELECT pair_id,rows,cols,data FROM two_view_geometries WHERE rows>0"):
            m = np.frombuffer(data, np.uint32).reshape(r, cols)[:, :2]
            tvg[pid_] = m
            total_tvg_corrs += r
        db.close()
        idx_cache = {}
        def sites(iid, xy):
            if iid not in idx_cache:
                d_ = {}
                for i, (x, y) in enumerate(kp[iid]):
                    d_.setdefault((float(x), float(y)), []).append(i)
                idx_cache[iid] = d_
            return idx_cache[iid].get((float(xy[0]), float(xy[1])), [])

        rep = {"counterfactual_graph": {
            "db_total_tvg_inlier_corrs": int(total_tvg_corrs),
            "npz_pairs": int(n),
            "would_be_growth_pct_if_new": round(100 * n / total_tvg_corrs, 2)}}

        # ---- per-run before/after (off x3 + densified control) ----
        runs = {}
        pts_ref = None; shift_ref = None
        for name in cfg["off"]:
            st, pts, shift = run_dir_stats(os.path.join(E9RUNS, name), pn, pd)
            runs[name] = st
            if name.endswith("_r1"):
                pts_ref, shift_ref = pts, shift
        if os.path.exists(os.path.join(cfg["densified"], "points3D.bin")):
            st, pts_d, _ = run_dir_stats(cfg["densified"], pn, pd)
            runs["densified_control"] = st
        rep["runs"] = runs

        # ---- npz pair -> reconstruction membership (reference: off_r1) ----
        obs2pid = {}
        for pid_, (_, track, _) in pts_ref.items():
            for iid, p2 in track:
                obs2pid[(int(iid), int(p2))] = pid_
        tlen = {pid_: len(t) for pid_, (_, t, _) in pts_ref.items()}
        cats = {"same_track": 0, "two_diff_tracks": 0, "one_side_in_track": 0, "unborn": 0}
        same_tl, same_ghost, unborn_ghost, diff_pairs_ex = [], 0, 0, []
        pid_xyz = {pid_: p for pid_, (p, _, _) in pts_ref.items()}
        for i in range(n):
            i1, i2 = int(f1[i]) + 1, int(f2[i]) + 1
            A = {obs2pid[(i1, u)] for u in sites(i1, xy1[i]) if (i1, u) in obs2pid}
            B = {obs2pid[(i2, v)] for v in sites(i2, xy2[i]) if (i2, v) in obs2pid}
            npz_fh = float(pos[i] @ pn + pd - shift_ref)
            in_band = GHOST_BAND[0] <= npz_fh < GHOST_BAND[1]
            if A & B:
                cats["same_track"] += 1
                t = max(tlen[p] for p in (A & B))
                same_tl.append(t)
                if in_band: same_ghost += 1
            elif A and B:
                cats["two_diff_tracks"] += 1
                if len(diff_pairs_ex) < 3:
                    pa, pb = next(iter(A)), next(iter(B))
                    diff_pairs_ex.append({
                        "d_3d_m": round(float(np.linalg.norm(pid_xyz[pa] - pid_xyz[pb])), 4),
                        "tl_a": tlen[pa], "tl_b": tlen[pb]})
            elif A or B:
                cats["one_side_in_track"] += 1
            else:
                cats["unborn"] += 1
                if in_band: unborn_ghost += 1
        same_tl = np.array(same_tl) if same_tl else np.zeros(0, int)
        rep["pair_membership_off_r1"] = {
            **cats,
            "same_track_len_2": int((same_tl == 2).sum()),
            "same_track_len_3plus": int((same_tl >= 3).sum()),
            "same_track_in_ghost_band": int(same_ghost),
            "unborn_in_ghost_band": int(unborn_ghost),
            "two_diff_track_examples": diff_pairs_ex,
        }
        # npz refit ghost-band composition (fixed plane, off_r1 anchor)
        fh_npz = pos @ pn + pd - shift_ref
        band = (fh_npz >= GHOST_BAND[0]) & (fh_npz < GHOST_BAND[1])
        rep["npz_refit_ghost_band"] = {
            "n_in_band": int(band.sum()),
            "pct": round(100 * float(band.mean()), 2),
            "e6_floor_h_raw_band": int(((fl_h >= GHOST_BAND[0]) & (fl_h < GHOST_BAND[1])).sum()),
            "dist_prod_p50_mm": round(float(np.median(dprod)) * 1000, 1),
        }

        # ---- parent-pair tri-ratio estimate (off_r1 state) vs re_min_ratio=0.2 ----
        parents = {}
        for i in range(n):
            i1, i2 = int(f1[i]) + 1, int(f2[i]) + 1
            a, b = (i1, i2) if i1 < i2 else (i2, i1)
            parents.setdefault(a * MAX_IMAGE_ID + b, 0)
            parents[a * MAX_IMAGE_ID + b] += 1
        ratios = []
        for pid_ in parents:
            m = tvg.get(pid_)
            if m is None: continue
            a, b = pid_ // MAX_IMAGE_ID, pid_ % MAX_IMAGE_ID
            tri = 0
            for u, v in m:
                pa = obs2pid.get((a, int(u))); pb = obs2pid.get((b, int(v)))
                if pa is not None and pa == pb: tri += 1
            ratios.append(tri / len(m))
        ratios = np.array(ratios)
        rep["parent_pair_tri_ratio_est"] = {
            "n_parent_pairs": len(parents),
            "p10": round(float(np.percentile(ratios, 10)), 3),
            "p50": round(float(np.percentile(ratios, 50)), 3),
            "below_re_min_ratio_0p2": int((ratios < 0.2).sum()),
            "note": "offline estimate: tri corr = TVG inlier with both endpoints in same 3D point (off_r1)",
        }
        report[cap] = rep
        print(cap, json.dumps(rep, indent=1))
    json.dump(report, open(f"{OUT}/f2_attribution.json", "w"), indent=1)
    print("WROTE", f"{OUT}/f2_attribution.json")

if __name__ == "__main__":
    main()
