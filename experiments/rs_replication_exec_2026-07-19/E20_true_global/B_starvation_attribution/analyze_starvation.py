#!/usr/bin/env python3.11
# E20-B device starvation attribution — telemetry-only reconciliation.
# Read-only over device pulls / E6 provenance / host replay runs.
# Writes JSON results next to itself. No production files touched.
import json, sqlite3, glob, os, sys
import numpy as np

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
EXP = f"{ROOT}/experiments/rs_replication_exec_2026-07-19"
OUT = f"{EXP}/E20_true_global/B_starvation_attribution"
CAPS = {"cap50": {"n_frames": 139, "throttle_frame": 31},
        "cap51": {"n_frames": 105, "throttle_frame": 36}}

def ply_vertex_count(path):
    with open(path, "rb") as f:
        head = f.read(4096).decode("latin1")
    for line in head.splitlines():
        if line.startswith("element vertex"):
            return int(line.split()[-1])
    return None

def pair_id(i1, i2):
    # colmap pair_id convention
    if i1 > i2: i1, i2 = i2, i1
    return i1 * 2147483647 + i2

res = {}
for cap, cfg in CAPS.items():
    pull = f"{ROOT}/data/pocketworld_captures/{cap}/device_full_pull_2026-07-17"
    seg = json.load(open(f"{pull}/finalize_segments.json"))
    meta = json.load(open(f"{pull}/sfm_sparse_meta.json"))

    # gpu fail pairs from device jsonl (live capture window)
    fails = []
    throttle_evt = None
    for line in open(f"{pull}/sfm_match_fail.jsonl"):
        e = json.loads(line)
        if e["type"] == "gpu_match_fail":
            fails.append(tuple(sorted(e["pair"])))
        elif e["type"] == "thermal_throttle":
            throttle_evt = e
    fail_set = set(fails)

    # db: image_id -> frame; matched pair set with verified geometry
    db = sqlite3.connect(f"file:{pull}/sfm_live.db?mode=ro", uri=True)
    imgs = {}
    for iid, name in db.execute("SELECT image_id, name FROM images"):
        imgs[iid] = name
    # verified pairs (two_view_geometries with rows>0)
    tvg_pairs = set()
    for (pid, rows) in db.execute("SELECT pair_id, rows FROM two_view_geometries"):
        if rows and rows > 0:
            i2 = pid % 2147483647; i1 = pid // 2147483647
            tvg_pairs.add((i1, i2))
    match_pairs = set()
    for (pid, rows) in db.execute("SELECT pair_id, rows FROM matches"):
        if rows and rows > 0:
            i2 = pid % 2147483647; i1 = pid // 2147483647
            match_pairs.add((i1, i2))
    db.close()

    # E6 provenance: candidate 2-view refits; "missing" = G1 dedup dist_prod>0.02
    z = np.load(f"{EXP}/E6_rescue_inject/{cap}/rescue_provenance_{cap}.npz", allow_pickle=True)
    f1, f2 = z["f1"], z["f2"]
    missing = z["dist_prod"] > 0.02
    inj = z["injected_mask"]
    df = np.abs(f1 - f2)
    tf = cfg["throttle_frame"]
    post_throttle = (np.maximum(f1, f2) >= tf)

    def band_stats(mask):
        n = int(mask.sum())
        b_le6 = int((mask & (df <= 6)).sum())
        b_7_12 = int((mask & (df >= 7) & (df <= 12)).sum())
        b_gt12 = int((mask & (df > 12)).sum())
        b_7_12_post = int((mask & (df >= 7) & (df <= 12) & post_throttle).sum())
        b_gt12_post = int((mask & (df > 12) & post_throttle).sum())
        gpu_fail_hit = int(sum(1 for a, b in zip(f1[mask], f2[mask])
                               if (min(a, b), max(a, b)) in fail_set))
        return {"n": n, "df<=6": b_le6, "df7-12": b_7_12, "df>12": b_gt12,
                "df7-12_post_throttle": b_7_12_post, "df>12_post_throttle": b_gt12_post,
                "pairs_in_gpu_fail_list": gpu_fail_hit}

    # unique pairs among missing points
    miss_pairs = set((min(a, b), max(a, b)) for a, b in zip(f1[missing], f2[missing]))
    inj_pairs = set((min(a, b), max(a, b)) for a, b in zip(f1[inj], f2[inj]))

    # frame-id -> image-id mapping check: db image names contain frame ids?
    # provenance f1/f2 came from the same db (S1), assume same id space.

    res[cap] = {
        "device_counters": {k: seg[k] for k in (
            "gpu_retry_attempts", "gpu_retry_recovered", "enrich_budget_stopped",
            "rematch_starved_frames", "rematch_candidates", "rematch_attempted",
            "rematch_written", "rematch_inliers", "rematch_budget",
            "repay_calls", "repay_attempted", "repay_written", "repay_inliers",
            "repay_skipped_thermal", "stage1_rounds", "stage1_ms", "enrich_ms",
            "stage2_ms", "total_ms", "upgrade_eligible", "upgrade_attempted",
            "upgrade_accepted", "theta_pre_n", "theta_pre_2view",
            "enrich_targeted_tracks", "enrich_targeted_scored")},
        "device_summary": meta["summary"],
        "gpu_fail_events_live": len(fails),
        "gpu_fail_unique_pairs": len(fail_set),
        "throttle_event": throttle_evt,
        "db": {"n_images": len(imgs), "match_pairs>0": len(match_pairs),
               "verified_pairs>0": len(tvg_pairs)},
        "e6_all_candidates": band_stats(np.ones_like(missing)),
        "e6_missing_points(G1 dist>2cm)": band_stats(missing),
        "e6_injected_final": band_stats(inj),
        "e6_missing_unique_pairs": len(miss_pairs),
        "e6_injected_unique_pairs": len(inj_pairs),
        "e6_missing_pairs_in_gpu_fail_list": len(miss_pairs & fail_set),
    }

    # host replay parity: vertex counts + counters
    host = {}
    for p in sorted(glob.glob(f"{EXP}/E9_birth_alias/runs/{cap}_off_r*/")) + \
             sorted(glob.glob(f"{EXP}/E19_no_birth/*/runs/{cap}_*/")):
        name = os.path.basename(p.rstrip("/"))
        seg_p = os.path.join(p, "finalize_segments.json")
        ply_p = os.path.join(p, "replay_finalize.ply")
        h = {}
        if os.path.exists(seg_p):
            hs = json.load(open(seg_p))
            h["counters"] = {k: hs.get(k) for k in (
                "gpu_retry_attempts", "enrich_budget_stopped", "rematch_candidates",
                "rematch_attempted", "rematch_written", "repay_written",
                "stage1_rounds", "stage1_ms", "enrich_ms", "stage2_ms",
                "upgrade_attempted", "upgrade_accepted", "theta_pre_n",
                "theta_pre_2view", "enrich_targeted_tracks")}
        if os.path.exists(ply_p):
            h["replay_finalize_ply_vertices"] = ply_vertex_count(ply_p)
        cl = os.path.join(p, "cloud.ply")
        if os.path.exists(cl):
            h["cloud_ply_vertices"] = ply_vertex_count(cl)
        host[name] = h
    res[cap]["host_runs"] = host
    res[cap]["device_ply_vertices"] = ply_vertex_count(f"{pull}/sfm_sparse.ply")

json.dump(res, open(f"{OUT}/reconciliation.json", "w"), indent=1)
print(json.dumps(res, indent=1))
