#!/usr/bin/env python3
"""把 arm C (旧 768 COLMAP 帧) 的网格搬进官方 SfM 帧: 用两套 sfm 共有的 132 个相机中心求 Umeyama Sim3。
用法: align_C.py <src.sfm 旧> <dst.sfm 官方> <in.obj> <out.obj>"""
import sys, json, os, numpy as np
SRC, DST, IN, OUT = sys.argv[1:5]
def centers(p):
    j = json.load(open(p))
    v = {}
    for x in j.get("views", []):
        v[str(x["poseId"])] = os.path.basename(x["path"])
    out = {}
    for x in j.get("poses", []):
        pid = str(x["poseId"])
        c = np.array([float(t) for t in x["pose"]["transform"]["center"]])
        if pid in v: out[v[pid]] = c
    return out
A, B = centers(SRC), centers(DST)
k = sorted(set(A) & set(B))
print(f"共有相机 {len(k)} (src {len(A)} / dst {len(B)})")
if len(k) < 10: raise SystemExit("共有相机太少, 停")
P = np.stack([A[i] for i in k]); Q = np.stack([B[i] for i in k])
mp, mq = P.mean(0), Q.mean(0)
X, Y = P - mp, Q - mq
U, S, Vt = np.linalg.svd(X.T @ Y / len(k))
d = np.sign(np.linalg.det(U @ Vt))
R = (Vt.T @ np.diag([1, 1, d]) @ U.T)
s = float(S[[0, 1, 2]].dot([1, 1, d]) / (X**2).sum() * len(k))
t = mq - s * R @ mp
res = np.linalg.norm((s * (R @ P.T).T + t) - Q, axis=1)
print(f"Sim3: scale {s:.6f}  残差 mm  p50 {1000*np.median(res):.2f}  p95 {1000*np.percentile(res,95):.2f}  max {1000*res.max():.2f}")
if np.median(res) > 0.05: raise SystemExit("对齐残差过大, 停 (两套 SfM 可能不是同一场)")
nv = nn = 0
with open(IN, errors="ignore") as f, open(OUT, "w") as g:
    for ln in f:
        if ln.startswith("v "):
            p = np.array([float(x) for x in ln.split()[1:4]]); q = s * (R @ p) + t
            g.write(f"v {q[0]:.6f} {q[1]:.6f} {q[2]:.6f}\n"); nv += 1
        elif ln.startswith("vn "):
            p = np.array([float(x) for x in ln.split()[1:4]]); q = R @ p
            g.write(f"vn {q[0]:.6f} {q[1]:.6f} {q[2]:.6f}\n"); nn += 1
        else: g.write(ln)
print(f"写出 {OUT}: {nv:,} 顶点 {nn:,} 法线")
