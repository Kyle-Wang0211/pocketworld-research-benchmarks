#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RGB <-> 深度 <-> 位姿 的光度自证。

cross_view_check 只验【深度+位姿+K】三者自洽, 对 RGB 是瞎的 ——
v2 把 RGB 从 vga_wide 换成 wide, 万一换错了(错帧/错相机/错朝向) cross_view 一声不吭。
所以这里用 i->j 的光度重投影: 用 depth_i + pose + K 把图 i warp 到视角 j, 与图 j 比。

四条腿 (同一批帧, 唯一变量是被检验的那一项):
  v2 正解       wide + highres_depth + wide_intrinsics + 插值位姿
  v2 错帧对照   RGB 换成【相邻那个 highres 时间戳】的 wide 图  <- 必须更差
  v2 写反对照   位姿求逆                                      <- 必须爆掉
  v1 对照       vga_wide + lowres_depth + vga_wide_intrinsics + 最近 traj 原值
"""
import argparse, glob, os, sys
import numpy as np, cv2
sys.path.insert(0, "/root/ta2"); sys.path.insert(0, "/root")
from ak_pose_interp import read_traj, TrajInterp

W, H = 768, 576


def ts_str(p):
    return os.path.basename(p).split("_", 1)[1].rsplit(".", 1)[0]


def rd_depth(p, mode="area"):
    d = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    if d is None:
        return None
    d = d.astype(np.float32) / 1000.
    if mode == "nearest":
        return cv2.resize(d, (W, H), interpolation=cv2.INTER_NEAREST)
    m = (d > 0).astype(np.float32)
    num = cv2.resize(d*m, (W, H), interpolation=cv2.INTER_AREA)
    den = cv2.resize(m,   (W, H), interpolation=cv2.INTER_AREA)
    o = np.zeros((H, W), np.float32); ok = den > 0; o[ok] = num[ok]/den[ok]; return o


def rd_gray(p):
    g = cv2.imread(p, cv2.IMREAD_GRAYSCALE)
    if g is None:
        return None
    return cv2.resize(g, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)


def rd_K(p):
    w, h, fx, fy, cx, cy = np.loadtxt(p)
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.]])
    K[0] *= W/float(w); K[1] *= H/float(h)
    return K


def photo(Ii, Ij, di, K, Ti, Tj, step=4):
    Ki = np.linalg.inv(K)
    ys, xs = np.mgrid[0:H:step, 0:W:step]
    z = di[ys, xs]; m = z > 0
    if m.sum() < 200:
        return None
    uv = np.stack([xs[m], ys[m], np.ones(m.sum())])
    cam = Ki @ (uv * z[m])
    Tji = np.linalg.inv(Tj) @ Ti
    cj = Tji[:3, :3] @ cam + Tji[:3, 3:4]
    good = cj[2] > 1e-6
    p = K @ cj[:, good]
    u = p[0]/p[2]; v = p[1]/p[2]
    ok = (u >= 0) & (u < W-1) & (v >= 0) & (v < H-1)
    if ok.sum() < 200:
        return None
    src = Ii[ys[m][good][ok], xs[m][good][ok]]
    dst = cv2.remap(Ij, u[ok].astype(np.float32).reshape(1, -1),
                    v[ok].astype(np.float32).reshape(1, -1), cv2.INTER_LINEAR).ravel()
    return float(np.median(np.abs(src - dst)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vd", required=True); ap.add_argument("--vid", required=True)
    ap.add_argument("--n", type=int, default=60)
    a = ap.parse_args()
    vd, vid = a.vd, a.vid
    ts_t, R_t, C_t = read_traj(os.path.join(vd, "lowres_wide.traj"))
    interp = TrajInterp(ts_t, R_t, C_t, max_gap=0.20)

    hs = sorted((ts_str(p) for p in glob.glob(os.path.join(vd, "highres_depth", "*.png"))), key=float)
    idx = list(range(0, len(hs)-1, max(1, (len(hs)-1)//a.n)))[:a.n]
    legs = {"v2 正解 (wide+FARO)": [], "v2 同帧但 RGB 退化到 640": [], "v2 错帧对照 (RGB 换邻帧)": [], "v2 写反对照": []}
    bl = []
    for i in idx:
        si, sj = hs[i], hs[i+1]
        if float(sj) - float(si) > 0.11:     # 只留 10 Hz 连拍内的相邻对, 让基线与 v1 可比
            continue
        Ti, Tj = interp(float(si)), interp(float(sj))
        if Ti is None or Tj is None:
            continue
        bl.append(float(np.linalg.norm(Ti[:3,3]-Tj[:3,3])))
        di = rd_depth("%s/highres_depth/%s_%s.png" % (vd, vid, si))
        Ii = rd_gray("%s/wide/%s_%s.png" % (vd, vid, si))
        Ij = rd_gray("%s/wide/%s_%s.png" % (vd, vid, sj))
        if di is None or Ii is None or Ij is None:
            continue
        K = rd_K("%s/wide_intrinsics/%s_%s.pincam" % (vd, vid, si))
        r = photo(Ii, Ij, di, K, Ti, Tj)
        if r is not None: legs["v2 正解 (wide+FARO)"].append(r)
        Ib = cv2.resize(cv2.resize(Ii, (640, 480), interpolation=cv2.INTER_AREA), (W, H),
                        interpolation=cv2.INTER_AREA)
        r = photo(Ib, cv2.resize(cv2.resize(Ij, (640, 480), interpolation=cv2.INTER_AREA), (W, H),
                                 interpolation=cv2.INTER_AREA), di, K, Ti, Tj)
        if r is not None: legs["v2 同帧但 RGB 退化到 640"].append(r)
        r = photo(Ij, Ij, di, K, Ti, Tj)          # 用【下一帧】的 RGB 冒充 i 的 RGB
        if r is not None: legs["v2 错帧对照 (RGB 换邻帧)"].append(r)
        r = photo(Ii, Ij, di, K, np.linalg.inv(Ti), np.linalg.inv(Tj))
        if r is not None: legs["v2 写反对照"].append(r)

    # v1 对照: vga_wide + lowres_depth, 只取 |Δt|<5ms 的帧 (v1 唯一收的那批)
    vs = sorted((ts_str(p) for p in glob.glob(os.path.join(vd, "vga_wide", "*.png"))), key=float)
    ex = [s for s in vs if abs(ts_t[int(np.abs(ts_t-float(s)).argmin())]-float(s)) < 0.005]
    v1 = []; bl2 = []
    if len(ex) > 4:
        jdx = list(range(0, len(ex)-1, max(1, (len(ex)-1)//a.n)))[:a.n]
        for i in jdx:
            si, sj = ex[i], ex[i+1]
            if float(sj) - float(si) > 0.11:
                continue
            bl2.append(0.0)
            ki = int(np.abs(ts_t-float(si)).argmin()); kj = int(np.abs(ts_t-float(sj)).argmin())
            Ti = np.eye(4); Ti[:3, :3] = R_t[ki]; Ti[:3, 3] = C_t[ki]
            Tj = np.eye(4); Tj[:3, :3] = R_t[kj]; Tj[:3, 3] = C_t[kj]
            di = rd_depth("%s/lowres_depth/%s_%s.png" % (vd, vid, si), "nearest")
            Ii = rd_gray("%s/vga_wide/%s_%s.png" % (vd, vid, si))
            Ij = rd_gray("%s/vga_wide/%s_%s.png" % (vd, vid, sj))
            if di is None or Ii is None or Ij is None:
                continue
            pc = None
            for c in (si, "%.3f" % (float(si)-.001), "%.3f" % (float(si)+.001)):
                p = "%s/vga_wide_intrinsics/%s_%s.pincam" % (vd, vid, c)
                if os.path.exists(p): pc = p; break
            if pc is None: continue
            r = photo(Ii, Ij, di, rd_K(pc), Ti, Tj)
            if r is not None: v1.append(r)
    legs["v1 对照 (vga+LiDAR, 精确位姿)"] = v1
    print("光度重投影 i->i+1 的 |ΔI| 中位 (灰度 0-255); v2 对的相机位移中位 %.4f m" % (np.median(bl) if bl else float("nan")))
    for k, v in legs.items():
        print("  %-30s %8.3f   (n=%d)" % (k, float(np.median(v)) if v else float("nan"), len(v)))


if __name__ == "__main__":
    main()
