#!/usr/bin/env python3
"""DA3 深度 + CasDiffMVS 官方几何一致性门。
   判据函数 check_geometric_consistency 与平均口径 (sum(reproj)+ref)/(geo_sum+1)
   逐字取自 /root/diffmvs/filter.py 的 filter_depth;常数取自 casdiffmvs_run_official.sh。
   depth_max/min 取自同一批 off768_true/cams/*_cam.txt 第 11 行(官方那次用的同一个值)。
   光度那一半用 DA3 自己的官方门 conf_thresh_percentile=40。"""
import sys, os, glob, numpy as np
sys.path.insert(0, "/root/diffmvs")
from filter import check_geometric_consistency
NPZ  = os.environ.get("NPZDIR", "/root/da3_r616")
PAIR = os.environ.get("PAIR", "/root/mono_data/scene0/pair.txt")
CAMS = os.environ.get("CAMS", "/root/off768_true/cams")
OUT  = os.environ.get("OUT",  "/root/bins_da3/da3r616_geo")
GEO_PIX, GEO_DEP, GEO_N = 1.0, 0.01, 3
d = np.load(sorted(glob.glob(f"{NPZ}/exports/npz/*.npz"))[0], allow_pickle=True)
D, C, E, K, I = d["depth"], d["conf"], d["extrinsics"], d["intrinsics"], d["image"]
N, H, W = D.shape
thr = float(np.percentile(C, 40.0))
rng = {}
for p in sorted(glob.glob(f"{CAMS}/*_cam.txt")):
    i = int(os.path.basename(p)[:8]); L = [l.rstrip() for l in open(p)]
    v = L[11].split(); a, b = float(v[0]), float(v[-1])
    rng[i] = (max(a,b), min(a,b))            # 官方 read_camera_parameters 返回 (depth_max, depth_min)
print(f"{N} 视图 {H}x{W}  conf p40={thr:.4f}  几何门 {GEO_PIX}px/{GEO_DEP*100:g}%/≥{GEO_N}"
      f"  深度范围[0]={rng[0]}", flush=True)
def E44(i):
    M = np.eye(4, dtype=np.float64); M[:3,:4] = E[i]; return M
pairs = []
with open(PAIR) as f:
    n = int(f.readline())
    for _ in range(n):
        r = int(f.readline().rstrip()); t = f.readline().rstrip().split()
        pairs.append((r, [int(x) for x in t[1::2]]))
u, v = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
P=[]; COL=[]; kept=0; tot=0; gsum_hist=[]
for ref, srcs in pairs:
    ref_d = D[ref].astype(np.float64); ref_K = K[ref].astype(np.float64); ref_E = E44(ref)
    dmax, dmin = rng[ref]
    assert dmax > dmin > 0, (dmax, dmin)      # 自证:顺序不许再反
    photo = C[ref] >= thr
    geo_sum = np.zeros((H,W), np.int32); reproj_sum = np.zeros((H,W), np.float64)
    for s in srcs:
        gm, dr, _, _ = check_geometric_consistency(
            ref_d, ref_K, ref_E, D[s].astype(np.float64), K[s].astype(np.float64), E44(s),
            dmax, dmin, GEO_PIX, GEO_DEP)
        geo_sum += gm.astype(np.int32); reproj_sum += dr
    gsum_hist.append(geo_sum.mean())
    m = photo & (geo_sum >= GEO_N) & (ref_d > 0)
    tot += int(photo.sum()); kept += int(m.sum())
    if not m.any(): continue
    depth_avg = ((reproj_sum + ref_d) / (geo_sum + 1))[m]      # 官方口径
    x = (u[m]-ref_K[0,2])/ref_K[0,0]*depth_avg; y = (v[m]-ref_K[1,2])/ref_K[1,1]*depth_avg
    Xc = np.stack([x,y,depth_avg],1); R = ref_E[:3,:3]; t = ref_E[:3,3]
    P.append(((Xc - t) @ R).astype(np.float32)); COL.append(I[ref][m].astype(np.uint8))
    if ref % 30 == 0: print(f"  ref{ref}: 光度后 {int(photo.sum()):,} -> 两半后 {int(m.sum()):,}"
                            f"  平均同意视图数 {geo_sum.mean():.2f}", flush=True)
print(f"平均同意视图数(全局) {np.mean(gsum_hist):.2f} / {len(pairs[0][1])} 邻居")
print(f"总计 光度后 {tot:,} -> 两半门后 {kept:,} ({100.0*kept/max(1,tot):.1f}%)")
if not P: print("零点通过,停"); sys.exit(1)
P=np.concatenate(P); COL=np.concatenate(COL)
P[:,1]*=-1; P[:,2]*=-1
os.makedirs(os.path.dirname(OUT), exist_ok=True)
P.tofile(OUT+".pos"); COL.tofile(OUT+".col")
print("点数", f"{len(P):,}", " 展示帧中位", np.round(np.median(P,0),3).tolist())
