#!/usr/bin/env python3
"""OBJ(无色) + 同源带色 PLY -> verdict-page 顶点色网格 bins, 输出格式与 /root/mesh2bins.py 逐字一致
(pos f32 / col u8 / nrm i8 / idx.k u32, 展示帧 y,z 取负)。
颜色用最近邻从 PLY 搬过来(meshFiltering 会改顶点数, 所以不能按序号对齐)。
  obj2meshbins.py <aligned.obj> <orig.obj 与PLY同帧> <colors.ply> <out_dir> <tag>"""
import sys, os, json, time, numpy as np
from plyfile import PlyData
from scipy.spatial import cKDTree
AOBJ, OOBJ, PLY, OUT, TAG = sys.argv[1:6]; CH_TRI = 40_000_000
os.makedirs(OUT, exist_ok=True); t0 = time.time()
def read_obj(p):
    V = []; F = []
    with open(p, errors="ignore") as f:
        for ln in f:
            if ln.startswith("v "): V.append(ln.split()[1:4])
            elif ln.startswith("f "):
                t = ln.split()[1:]
                F.append([int(x.split("/")[0]) for x in t[:3]])
    return np.asarray(V, dtype=np.float64), np.asarray(F, dtype=np.int64) - 1
V, F = read_obj(AOBJ); V0, _ = read_obj(OOBJ)
print(f"obj: {len(V):,} v  {len(F):,} f   ({time.time()-t0:.0f}s)", flush=True)
assert len(V) == len(V0), f"两个 obj 顶点数不同 {len(V)} vs {len(V0)}"
pl = PlyData.read(PLY)["vertex"]
P = np.stack([pl["x"], pl["y"], pl["z"]], 1).astype(np.float64)
C = np.stack([pl["red"], pl["green"], pl["blue"]], 1).astype(np.uint8)
d, i = cKDTree(P).query(V0, k=1, workers=-1)
print(f"颜色最近邻: {len(P):,} -> {len(V):,}  距离 mm p50 {1000*np.median(d):.2f} p95 {1000*np.percentile(d,95):.2f} max {1000*d.max():.1f}  ({time.time()-t0:.0f}s)", flush=True)
COL = C[i]
a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
fn = np.cross(b - a, c - a)
N = np.zeros_like(V)
for k in range(3): np.add.at(N, F[:, k], fn)
n = np.linalg.norm(N, axis=1, keepdims=True); n[n == 0] = 1; N = (N / n).astype(np.float32)
Vf = V.astype(np.float32)
Vf[:, 1] *= -1; Vf[:, 2] *= -1; N[:, 1] *= -1; N[:, 2] *= -1
N8 = np.clip(np.round(N * 127), -127, 127).astype(np.int8)
Vf.tofile(f"{OUT}/{TAG}.pos"); COL.tofile(f"{OUT}/{TAG}.col"); N8.tofile(f"{OUT}/{TAG}.nrm")
T = F.astype(np.uint32)
nparts = (len(T) + CH_TRI - 1) // CH_TRI
for k, off in enumerate(range(0, len(T), CH_TRI)):
    suf = "" if nparts == 1 else f".{k}"   # 页面单段请求 <tag>.idx, 多段才 <tag>.idx.k
    T[off:off + CH_TRI].astype("<u4").tofile(f"{OUT}/{TAG}.idx{suf}")
lo = np.percentile(Vf, 1, 0); hi = np.percentile(Vf, 99, 0); med = np.median(Vf, 0)
rad = float(np.percentile(np.linalg.norm(Vf - med, axis=1), 95))
mp = f"{OUT}/meta.json"; meta = json.load(open(mp)) if os.path.exists(mp) else {}
meta[TAG] = {"kind": "mesh", "n": int(len(Vf)), "tris": int(len(T)), "center": ((lo+hi)/2).tolist(),
             "ext": (hi-lo).tolist(), "med": med.astype(float).tolist(), "radius": rad,
             "idx_parts": int((len(T)+CH_TRI-1)//CH_TRI)}
json.dump(meta, open(mp, "w"), ensure_ascii=False, indent=1)
print(f"done {TAG}: {len(Vf):,} v / {len(T):,} tris  展示帧中位 {np.round(med,3).tolist()} radius {rad:.3f}  ({time.time()-t0:.0f}s)")
