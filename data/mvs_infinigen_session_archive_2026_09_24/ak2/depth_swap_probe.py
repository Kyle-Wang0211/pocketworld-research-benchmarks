#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单变量: 唯一变的是【深度来自哪里】, RGB/位姿/K/帧集合全部固定。
帧集合 = highres_depth 的时间戳 (它是 lowres_depth 时间戳的子集, 所以两种深度都能在同一时刻取到)。
  腿1 FARO  = highres_depth 1920x1440 -> 768x576 掩码归一 INTER_AREA
  腿2 LiDAR = lowres_depth  256x192   -> 768x576 INTER_NEAREST   (= v1 的口径)
  腿3 FARO 打乱对照 = FARO 深度整体乘 1.02 (2% 尺度错)           <- 判据必须报警
两个判据: 跨视深度一致性 |dz|、光度重投影 |ΔI|。
"""
import glob, os, sys
import numpy as np, cv2
sys.path.insert(0, "/root/ta2"); sys.path.insert(0, "/root")
from tartanair_to_blend import cross_view_check
from ak_pose_interp import read_traj, TrajInterp
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
W, H = 768, 576

def area(d):
    m = (d > 0).astype(np.float32)
    num = cv2.resize(d*m, (W, H), interpolation=cv2.INTER_AREA)
    den = cv2.resize(m,   (W, H), interpolation=cv2.INTER_AREA)
    o = np.zeros((H, W), np.float32); ok = den > 0; o[ok] = num[ok]/den[ok]; return o

def gray(p):
    g = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    return None if g is None else cv2.resize(g, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)

def photo(Ii, Ij, di, K, Ti, Tj, step=4):
    Ki = np.linalg.inv(K); ys, xs = np.mgrid[0:H:step, 0:W:step]
    z = di[ys, xs]; m = z > 0
    if m.sum() < 200: return None
    cam = Ki @ (np.stack([xs[m], ys[m], np.ones(m.sum())]) * z[m])
    Tji = np.linalg.inv(Tj) @ Ti
    cj = Tji[:3, :3] @ cam + Tji[:3, 3:4]; good = cj[2] > 1e-6
    p = K @ cj[:, good]; u = p[0]/p[2]; v = p[1]/p[2]
    ok = (u >= 0) & (u < W-1) & (v >= 0) & (v < H-1)
    if ok.sum() < 200: return None
    src = Ii[ys[m][good][ok], xs[m][good][ok]]
    dst = cv2.remap(Ij, u[ok].astype(np.float32).reshape(1,-1), v[ok].astype(np.float32).reshape(1,-1),
                    cv2.INTER_LINEAR).ravel()
    return float(np.median(np.abs(src-dst)))

vd, vid = sys.argv[1], sys.argv[2]
ts_t, R_t, C_t = read_traj(vd+"/lowres_wide.traj")
itp = TrajInterp(ts_t, R_t, C_t, max_gap=0.20)
hs = sorted((os.path.basename(p).split("_",1)[1][:-4] for p in glob.glob(vd+"/highres_depth/*.png")), key=float)
legs = {"FARO (highres_depth)":[], "LiDAR (lowres_depth, v1 口径)":[], "FARO x1.02 (尺度错 2%)":[]}
D = {k: [] for k in legs}; P = []; Ks = []
n = 0
TARGET = float(sys.argv[3]) if len(sys.argv) > 3 else 0.30   # 目标基线 m
Ts = [itp(float(s)) for s in hs]
Cs = np.array([(T[:3,3] if T is not None else [np.nan]*3) for T in Ts])
bls = []
for i in range(len(hs)-1):
    if Ts[i] is None: continue
    d2 = np.linalg.norm(Cs[i+1:] - Cs[i], axis=1)
    d2[~np.isfinite(d2)] = 1e9
    jj = int(np.argmin(np.abs(d2 - TARGET))) + i + 1
    if Ts[jj] is None or abs(np.linalg.norm(Cs[jj]-Cs[i]) - TARGET) > 0.05: continue
    if float(hs[jj]) - float(hs[i]) > 5.0: continue
    si, sj = hs[i], hs[jj]
    Ti, Tj = Ts[i], Ts[jj]
    bls.append(float(np.linalg.norm(Cs[jj]-Cs[i])))
    lp = "%s/lowres_depth/%s_%s.png" % (vd, vid, si)
    if not os.path.exists(lp): continue
    Ii, Ij = gray("%s/wide/%s_%s.png"%(vd,vid,si)), gray("%s/wide/%s_%s.png"%(vd,vid,sj))
    if Ii is None or Ij is None: continue
    K = np.loadtxt("%s/wide_intrinsics/%s_%s.pincam"%(vd,vid,si))
    K = np.array([[K[2],0,K[4]],[0,K[3],K[5]],[0,0,1.]]); K[0]*=W/1920.; K[1]*=H/1440.
    dh = area(cv2.imread("%s/highres_depth/%s_%s.png"%(vd,vid,si), cv2.IMREAD_UNCHANGED).astype(np.float32)/1000.)
    dl = cv2.resize(cv2.imread(lp, cv2.IMREAD_UNCHANGED).astype(np.float32)/1000., (W,H), interpolation=cv2.INTER_NEAREST)
    for nm, d in (("FARO (highres_depth)",dh), ("LiDAR (lowres_depth, v1 口径)",dl), ("FARO x1.02 (尺度错 2%)",dh*1.02)):
        r = photo(Ii, Ij, d, K, Ti, Tj)
        if r is not None: legs[nm].append(r)
    n += 1
    if n > 200: break
print("单变量深度对照  (n=%d 对, 基线中位 %.3f m, RGB=wide / K=wide_intrinsics / 位姿=插值, 全腿相同)" % (n, np.median(bls) if bls else float("nan")))
print("  %-32s %s" % ("深度来源", "光度重投影 |ΔI| 中位"))
for k, v in legs.items():
    print("  %-32s %8.3f  (n=%d)" % (k, float(np.median(v)) if v else float("nan"), len(v)))
