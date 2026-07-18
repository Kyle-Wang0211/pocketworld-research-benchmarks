#!/usr/bin/env python3
# E19-B Phase-0 forensics F1: are the E6 rescue npz pairs already present in the
# REPLAY db's keypoints / matches / two_view_geometries?
# Honest-first: this decides whether "injection" is a real delta or a no-op.
import json, sqlite3, sys
import numpy as np

MAX_IMAGE_ID = 2147483647
EXP = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19"
DATA = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures"

CFG = {
    "cap50": {
        "npz": f"{EXP}/E6_rescue_inject/cap50/rescue_provenance_cap50.npz",
        "replay_db": f"{DATA}/cap50/device_full_pull_2026-07-17/sfm_live.db",  # E9 recipe
        "e6_db": f"{DATA}/cap50/device_full_pull_2026-07-17/sfm_live.db",
    },
    "cap51": {
        "npz": f"{EXP}/E6_rescue_inject/cap51/rescue_provenance_cap51.npz",
        "replay_db": f"{DATA}/cap51/replay_database/sfm_live.db",              # E9 recipe
        "e6_db": f"{DATA}/cap51/device_full_pull_2026-07-17/sfm_live.db",
    },
}

def load_db(path):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c = db.cursor()
    kp = {}
    for iid, r, cols, data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
        if r == 0:
            kp[iid] = np.zeros((0, 2), np.float32)
            continue
        kp[iid] = np.frombuffer(data, dtype=np.float32).reshape(r, cols)[:, :2].copy()
    # matches (raw) and tvg inliers as index-pair sets per pair_id
    def pair_tab(table):
        out = {}
        for pid, r, cols, data in c.execute(f"SELECT pair_id,rows,cols,data FROM {table} WHERE rows>0"):
            m = np.frombuffer(data, dtype=np.uint32).reshape(r, cols)[:, :2]
            out[pid] = m
        return out
    matches = pair_tab("matches")
    tvg = pair_tab("two_view_geometries")
    ncams = c.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    db.close()
    return kp, matches, tvg, ncams

def xy_index(kp_arr):
    # exact float32 pixel -> list of kp indices (DSP-SIFT sites: one xy may have several variants)
    d = {}
    for i, (x, y) in enumerate(kp_arr):
        d.setdefault((float(x), float(y)), []).append(i)
    return d

def main():
    report = {}
    for cap, cfg in CFG.items():
        z = np.load(cfg["npz"], allow_pickle=True)
        f1, f2 = z["f1"], z["f2"]
        xy1, xy2 = z["xy1"].astype(np.float32), z["xy2"].astype(np.float32)
        n = len(f1)
        kp, matches, tvg, ncams = load_db(cfg["replay_db"])
        # per-image xy index, built lazily
        idx_cache = {}
        def sites(iid, xy):
            if iid not in idx_cache:
                idx_cache[iid] = xy_index(kp.get(iid, np.zeros((0, 2), np.float32)))
            return idx_cache[iid].get((float(xy[0]), float(xy[1])), [])
        # pair-level lookup sets
        tvg_sets = {pid: set(map(tuple, m.tolist())) for pid, m in tvg.items()}
        match_sets = {pid: set(map(tuple, m.tolist())) for pid, m in matches.items()}
        tvg_count = {pid: len(m) for pid, m in tvg.items()}

        kp_hit = 0            # both endpoints exist as keypoints (exact xy)
        tvg_pair_row = 0      # (f1,f2) pair has a TVG row
        corr_in_tvg = 0       # the exact correspondence (some site combo) is a TVG inlier
        corr_in_matches = 0   # ... present in raw matches
        parent_inl = np.zeros(n, np.int32)
        gap = np.abs(f1 - f2)
        examples_missing = []
        for i in range(n):
            i1, i2 = int(f1[i]) + 1, int(f2[i]) + 1
            s1 = sites(i1, xy1[i]); s2 = sites(i2, xy2[i])
            if s1 and s2:
                kp_hit += 1
            else:
                if len(examples_missing) < 5:
                    examples_missing.append({"i": i, "f1": int(f1[i]), "f2": int(f2[i]),
                                             "xy1": xy1[i].tolist(), "xy2": xy2[i].tolist(),
                                             "s1": len(s1), "s2": len(s2)})
                continue
            a, b = (i1, i2) if i1 < i2 else (i2, i1)
            pid = a * MAX_IMAGE_ID + b
            swapped = i1 > i2
            ts = tvg_sets.get(pid); ms = match_sets.get(pid)
            if ts is not None:
                tvg_pair_row += 1
                parent_inl[i] = tvg_count.get(pid, 0)
            found_t = found_m = False
            for u in s1:
                for v in s2:
                    key = (v, u) if swapped else (u, v)
                    if ts is not None and key in ts:
                        found_t = True
                    if ms is not None and key in ms:
                        found_m = True
                if found_t and found_m:
                    break
            corr_in_tvg += found_t
            corr_in_matches += found_m
        rep = {
            "n_pairs": int(n),
            "replay_db": cfg["replay_db"],
            "db_same_as_e6_source": cfg["replay_db"] == cfg["e6_db"],
            "n_images_db": int(ncams),
            "both_keypoints_exist_exact_xy": int(kp_hit),
            "parent_pair_has_tvg_row": int(tvg_pair_row),
            "correspondence_in_tvg_inliers": int(corr_in_tvg),
            "correspondence_in_raw_matches": int(corr_in_matches),
            "parent_tvg_inliers_lt15": int(((parent_inl > 0) & (parent_inl < 15)).sum()),
            "parent_tvg_inliers_p50": float(np.median(parent_inl[parent_inl > 0])) if (parent_inl > 0).any() else None,
            "frame_gap_hist": {"le12": int((gap <= 12).sum()), "13_30": int(((gap > 12) & (gap <= 30)).sum()),
                                "gt30": int((gap > 30).sum()), "p50": float(np.median(gap)), "max": int(gap.max())},
            "examples_missing_keypoints": examples_missing,
        }
        report[cap] = rep
        print(cap, json.dumps(rep, indent=1))
    out = f"{EXP}/E19_no_birth/B_match_enrichment/f1_presence.json"
    json.dump(report, open(out, "w"), indent=1)
    print("WROTE", out)

if __name__ == "__main__":
    main()
