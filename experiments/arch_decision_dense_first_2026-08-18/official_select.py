#!/usr/bin/env python3
"""全场景官方选源:OpenMVS Scene::SelectNeighborViews + FilterNeighborViews 逐字复刻。

公式与参数全部来自 OpenMVS v2.4.0(e2f38b4)源码考古(file:line 见考古报告),
本文件是公式的独立 Python 重写——不含任何 AGPL 代码文本:
  Scene.cpp:843-981  打分主体(Goesele 2007 风格)
    sigmaSmall = -1/(2*(0.38*θopt)^2), sigmaLarge = -1/(2*(0.7*θopt)^2)   [:867-868]
    wAngle = exp((angle-θopt)^2 * (angle<θopt ? sigmaSmall : sigmaLarge)) [:900]
    footprint = f/depth [Camera.h:430-432];r = fp_ref/fp_src
    wScale: r>1.6→(1.6/r)^2; 1<=r<=1.6→1; r<1→r^2                        [:904-909]
    score += max(wAngle, 0.1) * wScale                                    [:911]
    准入:共享点数>3 [:928];neighbor.score = Σscore * max(area,0.01)      [:961]
    area = 共视点双双在界内的 ref 投影,16×16 网格占据率 [Util.inl:945-963]
  Scene.cpp:1000-1015 FilterNeighborViews
    keepMin = max(4, nMaxViews*3/4);从尾剔除 area<0.05 或 scale∉[0.2,3.2]
    或 avgAngle∉[3°,65°](仅当剩余>keepMin);截断到 nMaxViews
  OPTDENSE 默认 [DepthMap.cpp:84-101]:fOptimAngle=12°,fMinArea=0.05,
    fMinAngle=3°,fMaxAngle=65°;nMaxViews 我们取 10(管线接口 num_view=10,
    OpenMVS 默认 12——这是唯一按我方接口取的参数,其余全默认)。
"""
import json
import os
import sys
import time

import numpy as np

REPO = os.path.expanduser(
    "~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
sys.path.insert(0, REPO)
import colmap_input as CI                                    # noqa: E402

BASE = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
HERE = os.path.dirname(os.path.abspath(__file__))
THETA_OPT = np.deg2rad(12.0)
SIG_SMALL = -1.0 / (2 * (0.38 * THETA_OPT) ** 2)
SIG_LARGE = -1.0 / (2 * (0.7 * THETA_OPT) ** 2)
N_MAX = 10
KEEP_MIN = max(4, N_MAX * 3 // 4)          # =7
F_MIN_AREA, MIN_ANG, MAX_ANG = 0.05, 3.0, 65.0
GRID = 16

t0 = time.time()
cameras, images, points3d = CI.read_model(BASE + "/in_P16k/sparse", ".bin")
assert len(images) == 132
W = {cid: cameras[cid].width for cid in cameras}
Hh = {cid: cameras[cid].height for cid in cameras}
FX = {cid: cameras[cid].params[0] for cid in cameras}

ext, K, C, fx, wh = [], [], [], [], []
for im in images:
    R = CI.quaternion_to_rotation_matrix(im.qvec)
    t = np.asarray(im.tvec)
    ext.append((np.asarray(R), t))
    C.append(-np.asarray(R).T @ t)
    cid = im.camera_id
    p = cameras[cid].params            # PINHOLE fx fy cx cy
    K.append(np.array([[p[0], 0, p[2]], [0, p[1], p[3]], [0, 0, 1]]))
    fx.append(p[0]); wh.append((W[cid], Hh[cid]))

# 点云与可见性
pids = sorted(points3d.keys())
pid2row = {p: i for i, p in enumerate(pids)}
XYZ = np.array([points3d[p].xyz for p in pids])
vis = []                                # 每图可见点的行号(升序)
for im in images:
    rows = sorted(pid2row[p] for p in im.point3d_ids if p != -1 and p in pid2row)
    vis.append(np.array(rows, dtype=np.int64))
print(f"载入 {time.time()-t0:.1f}s  点 {len(pids):,}", flush=True)

def project(i, X):
    R, t = ext[i]
    xc = X @ R.T + t
    z = xc[:, 2]
    uv = (xc @ K[i].T)
    uv = uv[:, :2] / np.maximum(z[:, None], 1e-9)
    w, h = wh[i]
    inside = (z > 0) & (uv[:, 0] >= 0) & (uv[:, 0] < w) & (uv[:, 1] >= 0) & (uv[:, 1] < h)
    return uv, z, inside

sel_all, stats = {}, {}
for a in range(132):
    cand = []
    for b in range(132):
        if b == a:
            continue
        shared = np.intersect1d(vis[a], vis[b], assume_unique=True)
        if len(shared) <= 3:                                    # Scene.cpp:928
            continue
        X = XYZ[shared]
        va = C[a] - X; vb = C[b] - X
        na = np.linalg.norm(va, axis=1); nb = np.linalg.norm(vb, axis=1)
        cosang = np.clip((va * vb).sum(1) / np.maximum(na * nb, 1e-12), -1, 1)
        ang = np.arccos(cosang)
        sig = np.where(ang < THETA_OPT, SIG_SMALL, SIG_LARGE)
        w_ang = np.exp((ang - THETA_OPT) ** 2 * sig)
        # footprint 比:f/depth;流式单相机 f 同 ⇒ 比值=depth_b/depth_a,仍按原式写
        Ra, ta = ext[a]; Rb, tb = ext[b]
        da = (X @ Ra.T + ta)[:, 2]; db = (X @ Rb.T + tb)[:, 2]
        r = (fx[a] / np.maximum(da, 1e-9)) / np.maximum(fx[b] / np.maximum(db, 1e-9), 1e-12)
        w_scale = np.where(r > 1.6, (1.6 / r) ** 2, np.where(r >= 1.0, 1.0, r ** 2))
        score = (np.maximum(w_ang, 0.1) * w_scale).sum()
        # 覆盖面积:双双在界内的 ref 投影 16×16 占据率
        uva, _, ina = project(a, X)
        _, _, inb = project(b, X)
        ok = ina & inb
        if ok.any():
            wA, hA = wh[a]
            gx = np.clip((uva[ok, 0] / wA * GRID).astype(int), 0, GRID - 1)
            gy = np.clip((uva[ok, 1] / hA * GRID).astype(int), 0, GRID - 1)
            area = len(np.unique(gx * GRID + gy)) / (GRID * GRID)
        else:
            area = 0.0
        cand.append(dict(b=b, score=float(score * max(area, 0.01)),
                         area=float(area),
                         avg_ang=float(np.degrees(ang.mean())),
                         avg_scale=float(r.mean()), n=int(len(shared))))
    cand.sort(key=lambda d: -d["score"])
    # FilterNeighborViews(Scene.cpp:1000-1015)
    kept = list(cand)
    i = len(kept) - 1
    while i >= 0 and len(kept) > KEEP_MIN:
        d = kept[i]
        if d["area"] < F_MIN_AREA or not (0.2 <= d["avg_scale"] <= 3.2) \
           or not (MIN_ANG <= d["avg_ang"] <= MAX_ANG):
            kept.pop(i)
        i -= 1
    kept = kept[:N_MAX]
    sel_all[a] = kept
    stats[a] = dict(n_cand=len(cand), sel=[d["b"] for d in kept],
                    ang_p50=float(np.median([d["avg_ang"] for d in kept])) if kept else 0)
    if a % 30 == 0:
        print(f"  ref {a}/132  {time.time()-t0:.0f}s", flush=True)

# 与现行 pair.txt 对比
old = {}
with open(BASE + "/mvs_P16k/pair.txt") as f:
    n = int(f.readline())
    for _ in range(n):
        r = int(f.readline()); toks = f.readline().split()
        old[r] = [int(toks[1 + 2 * i]) for i in range(int(toks[0]))]

changed = [a for a in range(132) if [d["b"] for d in sel_all[a]] != old.get(a, [])]
print(f"\n选源完成 {time.time()-t0:.0f}s;源集变化 {len(changed)}/132 个 ref")
ang_new = [stats[a]["ang_p50"] for a in range(132)]
print(f"新选源平均角 p50={np.median(ang_new):.1f}°(现行实选 8.7°,OpenMVS 目标 12°)")

with open(os.path.join(HERE, "pair_official.txt"), "w") as f:
    f.write("132\n")
    for a in range(132):
        kept = sel_all[a]
        f.write(f"{a}\n{len(kept)} ")
        f.write(" ".join(f"{d['b']} {max(d['score'], 1.0):.4f}" for d in kept) + "\n")
json.dump(dict(changed=changed, stats={str(k): v for k, v in stats.items()}),
          open(os.path.join(HERE, "official_selection.json"), "w"))
print("已写 pair_official.txt / official_selection.json")
