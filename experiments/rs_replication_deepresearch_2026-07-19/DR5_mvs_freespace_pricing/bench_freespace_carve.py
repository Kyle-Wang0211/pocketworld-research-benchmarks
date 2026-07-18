#!/usr/bin/env python3.11
"""DR5 spike: free-space carving 微基准(定价用,非实现承诺)。

kernel:点云逐点投影到每视深度图,判 free-space violation
  (点在相机与测量表面之间 => 该视对该点投"鬼票")。
数据:cap50 真实 sfm_sparse.ply(92,849 点)+ 5 张真实 L1 深度(512x896 双通道 depth/conf)
      + sfm_sparse_meta.json 真实位姿 + 生产 load_frames 的 K。
计时:同进程 back-to-back 多轮,报 median(遵守热受控计时纪律)。
只读数据,只写本目录。
"""
import json, struct, subprocess, sys, time, types
from pathlib import Path
import numpy as np

REPO = Path("/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714")
CAP = REPO / "data/pocketworld_captures/cap50"
D = CAP / "device_full_pull_2026-07-17"
OUT = REPO / "experiments/rs_replication_deepresearch_2026-07-19/DR5_mvs_freespace_pricing"

# ---- 复用生产口径的 frame 加载(与 04_merrell_netvote/probe_depth_calib.py 同源) ----
REV = "f2fc9a1"
SRC = "experiments/floor_plane_sweep_densifier_2026-07-13/fr_planesweep_wall_ceiling.py"
payload = subprocess.check_output(["git", "-C", str(REPO), "show", f"{REV}:{SRC}"])
m = types.ModuleType("pin"); m.__file__ = "pin"; sys.modules["pin"] = m
exec(compile(payload, m.__file__, "exec"), m.__dict__)
frames = m.load_frames(CAP / "private_manifests/subset_meta_cap50full.json",
                       CAP / "private_manifests/sfm_fed_frames.jsonl",
                       CAP / "raw/photos_highres")
fbyid = {int(f.frame_id): f for f in frames}

def load_l1(fid):
    b = open(D / f"l1_depth_{fid}.bin", "rb").read()
    magic, ver, f_, H, W = struct.unpack("<5i", b[:20])
    data = np.frombuffer(b, dtype="<f4", offset=20)
    return data[:H*W].reshape(H, W).copy(), data[H*W:2*H*W].reshape(H, W).copy(), H, W

def load_ply_binary(p):
    raw = open(p, "rb").read()
    i = raw.index(b"end_header\n") + len(b"end_header\n")
    n = int([l for l in raw[:i].split(b"\n") if l.startswith(b"element vertex")][0].split()[-1])
    dt = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
    a = np.frombuffer(raw, dtype=dt, count=n, offset=i)
    return np.stack([a["x"], a["y"], a["z"]], axis=1).astype(np.float64)

xyz = load_ply_binary(D / "sfm_sparse.ply")
N = len(xyz)
FIDS = [2, 20, 83, 128, 129]

# ---- carving kernel(单帧) ----
CONF_MIN = 0.5
MARGIN = 0.10  # m,free-space 违规余量(与 probe_depth_calib 口径一致)

def carve_one(f, depth, conf, H, W, pts):
    cam = (f.R @ pts.T).T + f.t
    z = cam[:, 2]
    front = z > 0.05
    homo = (f.K @ cam.T).T
    u = homo[:, 0] / z; v = homo[:, 1] / z
    sx = W / f.width; sy = H / f.height
    ud = u * sx; vd = v * sy
    inb = front & (ud >= 0) & (ud < W - 1) & (vd >= 0) & (vd < H - 1)
    ui = np.clip(np.round(ud).astype(np.int32), 0, W - 1)
    vi = np.clip(np.round(vd).astype(np.int32), 0, H - 1)
    dl1 = depth[vi, ui]; cl1 = conf[vi, ui]
    valid = inb & (cl1 > CONF_MIN) & (dl1 > 0)
    violation = valid & (z < dl1 - MARGIN)   # 点悬在测量表面之前 => free-space 违规票
    return valid, violation

# ---- 微基准:预载 5 帧深度(模拟稠密段深度已在内存/mmap),纯 carve 计时 ----
loaded = []
for fid in FIDS:
    depth, conf, H, W = load_l1(fid)
    loaded.append((fbyid[fid], depth, conf, H, W))

# 预热
for f, depth, conf, H, W in loaded:
    carve_one(f, depth, conf, H, W, xyz)

ROUNDS = 8
per_frame_ms = []
for _ in range(ROUNDS):
    for f, depth, conf, H, W in loaded:
        t0 = time.perf_counter()
        carve_one(f, depth, conf, H, W, xyz)
        per_frame_ms.append((time.perf_counter() - t0) * 1e3)
per_frame_ms = np.array(per_frame_ms)

# 磁盘 IO 成本(流式逐帧读 3.67MB bin)
io_ms = []
for _ in range(4):
    for fid in FIDS:
        t0 = time.perf_counter()
        load_l1(fid)
        io_ms.append((time.perf_counter() - t0) * 1e3)
io_ms = np.array(io_ms)

# ---- 5 帧真实票统计(coverage 证据,不是最终裁决) ----
valid_cnt = np.zeros(N, np.int32)
viol_cnt = np.zeros(N, np.int32)
for f, depth, conf, H, W in loaded:
    valid, viol = carve_one(f, depth, conf, H, W, xyz)
    valid_cnt += valid
    viol_cnt += viol

stats = {
    "n_points": int(N),
    "n_frames_bench": len(FIDS),
    "carve_ms_per_frame": {
        "median": float(np.median(per_frame_ms)),
        "p10": float(np.percentile(per_frame_ms, 10)),
        "p90": float(np.percentile(per_frame_ms, 90)),
        "rounds": ROUNDS,
    },
    "io_ms_per_frame": {
        "median": float(np.median(io_ms)),
        "p90": float(np.percentile(io_ms, 90)),
    },
    "extrapolation_139_frames": {
        "carve_total_s": float(np.median(per_frame_ms) * 139 / 1e3),
        "carve_plus_io_total_s": float((np.median(per_frame_ms) + np.median(io_ms)) * 139 / 1e3),
    },
    "coverage_5frames": {
        "mean_valid_frac_per_frame": float(valid_cnt.mean() / len(FIDS)),
        "pts_valid_ge1": float((valid_cnt >= 1).mean()),
        "pts_valid_ge2": float((valid_cnt >= 2).mean()),
        "pts_valid_ge3": float((valid_cnt >= 3).mean()),
        "pts_viol_ge1": float((viol_cnt >= 1).mean()),
        "pts_viol_ge2": float((viol_cnt >= 2).mean()),
        "mean_valid_per_point": float(valid_cnt.mean()),
    },
    "memory_notes": {
        "one_depth_map_MB": 512 * 896 * 2 * 4 / 1e6,
        "streaming_accumulators_MB": (N * 4 * 2) / 1e6,
        "all_139_depths_if_resident_MB": 512 * 896 * 2 * 4 * 139 / 1e6,
    },
}
(OUT / "bench_results.json").write_text(json.dumps(stats, indent=2))
print(json.dumps(stats, indent=2))
