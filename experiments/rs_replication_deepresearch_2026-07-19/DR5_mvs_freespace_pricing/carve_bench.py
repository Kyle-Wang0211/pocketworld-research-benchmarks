#!/usr/bin/env python3.11
"""DR5 spike: free-space carving microbenchmark on cap50 L1 depth maps.

Kernel: project full sparse cloud (92,849 pts) into each per-view depth map,
count free-space violations (point lies strictly in front of observed surface
=> camera saw *through* the point => evidence the point is a false positive).

Data (read-only):
  - l1_depth_<fid>.bin : 20B header "L1DP",ver,channels=2,h=512,w=896; then
    h*w float32 depth followed by h*w float32 conf (plane-major).
  - arbitration_plan.json : per-ref stage4 blocks = [W2C 4x4 row-major | K 3x3 | pad]
    stage4 K matches 896x512 exactly (cx~448, cy~256).
  - sfm_sparse.ply : binary_little_endian, 92,849 x (3f + 3B).

Outputs bench JSON to stdout + results file. No source tree touched.
"""
import json, struct, sys, time
import numpy as np

D = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/data/pocketworld_captures/cap50/device_full_pull_2026-07-17"
OUT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_deepresearch_2026-07-19/DR5_mvs_freespace_pricing"

MARGIN_REL = 0.03   # 3% relative depth margin (conservative vs L1 band logic)
CONF_MIN = 0.5      # only trust confident depth pixels

def load_ply(path):
    with open(path, "rb") as f:
        hdr = b""
        while not hdr.endswith(b"end_header\n"):
            hdr += f.readline()
        n = int([l for l in hdr.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
        rec = np.dtype([("xyz", "<f4", 3), ("rgb", "u1", 3)])
        data = np.frombuffer(f.read(n * rec.itemsize), dtype=rec)
    return np.ascontiguousarray(data["xyz"].astype(np.float64)), n

def load_depth(fid):
    with open(f"{D}/l1_depth_{fid}.bin", "rb") as f:
        # header: magic, version, frame_id, h, w ; payload = h*w depth f32 + h*w conf f32
        magic, ver, hdr_fid, h, w = struct.unpack("<4siiii", f.read(20))
        assert magic == b"L1DP" and hdr_fid == fid, (magic, ver, hdr_fid, h, w)
        buf = np.frombuffer(f.read(h * w * 2 * 4), dtype="<f4")
    depth = buf[: h * w].reshape(h, w).astype(np.float64)
    conf = buf[h * w :].reshape(h, w).astype(np.float64)
    return depth, conf, h, w

def main():
    plan = json.load(open(f"{D}/arbitration_plan.json"))
    pts, npts = load_ply(f"{D}/sfm_sparse.ply")
    pts_h = np.hstack([pts, np.ones((npts, 1))])

    import os
    views = []
    for r in plan["refs"]:
        if not os.path.exists(f"{D}/l1_depth_{r['frame_id']}.bin"):
            continue  # plan had 8 refs; only 5 depth maps were persisted on device
        blk = np.array(r["proj"]["stage4"], dtype=np.float64)
        # ref view = first 32-float block: 16 (W2C 4x4 row-major) + 16 (K as 4x4)
        W2C = blk[:16].reshape(4, 4)
        K4 = blk[16:32].reshape(4, 4)
        K = K4[:3, :3]
        depth, conf, h, w = load_depth(r["frame_id"])
        valid = (depth > 0) & (conf >= CONF_MIN)
        views.append(dict(fid=r["frame_id"], W2C=W2C, K=K, depth=depth,
                          conf=conf, h=h, w=w, valid_frac=float(valid.mean())))

    def carve_one(v):
        cam = pts_h @ v["W2C"].T          # Nx4
        z = cam[:, 2]
        infront = z > 0.05
        u = v["K"][0, 0] * cam[:, 0] / z + v["K"][0, 2]
        vv = v["K"][1, 1] * cam[:, 1] / z + v["K"][1, 2]
        inb = infront & (u >= 0) & (u < v["w"] - 1) & (vv >= 0) & (vv < v["h"] - 1)
        ui = np.clip(u.astype(np.int32), 0, v["w"] - 1)
        vi = np.clip(vv.astype(np.int32), 0, v["h"] - 1)
        d = v["depth"][vi, ui]
        c = v["conf"][vi, ui]
        obs = inb & (d > 0) & (c >= CONF_MIN)
        viol = obs & (z < d * (1.0 - MARGIN_REL))
        behind = obs & (z > d * (1.0 + MARGIN_REL))
        onsurf = obs & ~viol & ~behind
        return obs, viol, behind, onsurf

    # warm + timed runs (back-to-back, same process, per CLAUDE.md timing culture)
    REPS = 20
    for v in views:
        carve_one(v)  # warm
    per_view_ms = {}
    obs_cnt = np.zeros(npts, np.int32); viol_cnt = np.zeros(npts, np.int32)
    behind_cnt = np.zeros(npts, np.int32); onsurf_cnt = np.zeros(npts, np.int32)
    for v in views:
        t0 = time.perf_counter()
        for _ in range(REPS):
            obs, viol, behind, onsurf = carve_one(v)
        dt = (time.perf_counter() - t0) / REPS * 1000
        per_view_ms[v["fid"]] = round(dt, 3)
        obs_cnt += obs; viol_cnt += viol; behind_cnt += behind; onsurf_cnt += onsurf

    ms = sorted(per_view_ms.values())
    med_ms = ms[len(ms) // 2]

    res = dict(
        n_points=npts,
        n_views=len(views),
        margin_rel=MARGIN_REL, conf_min=CONF_MIN, reps=REPS,
        per_view_carve_ms=per_view_ms,
        median_carve_ms_per_view=med_ms,
        extrapolated_139_views_s=round(med_ms * 139 / 1000, 3),
        depth_valid_frac_per_view={v["fid"]: round(v["valid_frac"], 4) for v in views},
        points_observed_ge1=int((obs_cnt >= 1).sum()),
        points_observed_ge1_frac=round(float((obs_cnt >= 1).mean()), 4),
        points_observed_ge2=int((obs_cnt >= 2).sum()),
        mean_obs_per_point=round(float(obs_cnt.mean()), 3),
        points_violation_ge1=int((viol_cnt >= 1).sum()),
        points_violation_ge2=int((viol_cnt >= 2).sum()),
        points_violation_ge2_frac=round(float((viol_cnt >= 2).mean()), 4),
        points_behind_ge1=int((behind_cnt >= 1).sum()),
        points_onsurf_ge1=int((onsurf_cnt >= 1).sum()),
        # of observed points, vote split
        viol_share_of_observations=round(float(viol_cnt.sum()) / max(1, int(obs_cnt.sum())), 4),
    )
    json.dump(res, open(f"{OUT}/bench_results.json", "w"), indent=2)
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
