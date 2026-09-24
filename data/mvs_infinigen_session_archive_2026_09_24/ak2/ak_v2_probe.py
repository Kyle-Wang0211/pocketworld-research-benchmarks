#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 的端到端自证探针 (不写盘)。

--what pose   : 插值位姿在【真实工况】上的跨视自证 (配对比较, 不是 6 个样本的中位数)
                A 精确组  = |Δt|<5ms 的帧 (v1 唯一收的那批), 用 traj 原值
                B 插值组  = |Δt|>=5ms 的帧 (v1 全扔的那批), 用插值位姿   <- 要 ≈ A
                C 最近邻组= 同 B 的帧, 改用最近 traj 原值 (朴素放宽容差)  <- 必须更差
                D 写反组  = 同 B 的帧, 位姿求逆                            <- 必须爆掉
--what depth  : highres_depth 的洞 / 降采样口径 / 与 lowres 上采样的差
--what k3     : wide_intrinsics 与 vga_wide_intrinsics 的 x3 关系, 端到端
"""
import argparse, glob, os, sys
import numpy as np, cv2
sys.path.insert(0, "/root/ta2"); sys.path.insert(0, "/root")
from tartanair_to_blend import cross_view_check, frame_range
from ak_pose_interp import read_traj, TrajInterp

W, H = 768, 576


def ts_str(p):
    return os.path.basename(p).split("_", 1)[1].rsplit(".", 1)[0]


def resize_depth(d, mode):
    if mode == "nearest":
        return cv2.resize(d, (W, H), interpolation=cv2.INTER_NEAREST)
    m = (d > 0).astype(np.float32)
    num = cv2.resize(d * m, (W, H), interpolation=cv2.INTER_AREA)
    den = cv2.resize(m, (W, H), interpolation=cv2.INTER_AREA)
    o = np.zeros((H, W), np.float32); ok = den > 0; o[ok] = num[ok] / den[ok]
    return o


def load(vd, vid, s, imgdir, depdir, intrdir, native, mode="area"):
    dp = os.path.join(vd, depdir, "%s_%s.png" % (vid, s))
    d = cv2.imread(dp, cv2.IMREAD_UNCHANGED)
    if d is None:
        return None
    d = d.astype(np.float32) / 1000.0
    pc = None
    for c in (s, "%.3f" % (float(s) - .001), "%.3f" % (float(s) + .001)):
        p = os.path.join(vd, intrdir, "%s_%s.pincam" % (vid, c))
        if os.path.exists(p):
            pc = p; break
    if pc is None:
        return None
    w, h, fx, fy, cx, cy = np.loadtxt(pc)
    K = np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]])
    K[0] *= W / float(w); K[1] *= H / float(h)
    return resize_depth(d, mode), K


def pose_leg(vd, vid, stamps, poses, imgdir, depdir, intrdir, native, n, mode="area"):
    """对给定 (时间戳, 位姿) 列表跑 cross_view_check, 用 n 个样本点。"""
    ds, Ks, Ps = [], [], []
    for s, T in zip(stamps, poses):
        r = load(vd, vid, s, imgdir, depdir, intrdir, native, mode)
        if r is None:
            continue
        ds.append(r[0]); Ks.append(r[1]); Ps.append(T)
    if len(ds) < 4:
        return float("inf"), 0
    return cross_view_check(Ps, ds, Ks[0], n=n), len(ds)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vd", required=True)
    ap.add_argument("--vid", required=True)
    ap.add_argument("--what", default="pose")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--stride_b", type=int, default=0)
    a = ap.parse_args()
    vd, vid = a.vd, a.vid
    ts_t, R_t, C_t = read_traj(os.path.join(vd, "lowres_wide.traj"))
    interp = TrajInterp(ts_t, R_t, C_t, max_gap=0.20, space="c2w")

    if a.what == "pose":
        imgdir, depdir, intrdir, native = "vga_wide", "lowres_depth", "vga_wide_intrinsics", (640, 480)
        stamps = sorted((ts_str(p) for p in glob.glob(os.path.join(vd, imgdir, "*.png"))), key=float)
        exact, interpo = [], []
        for s in stamps:
            t = float(s)
            k = int(np.abs(ts_t - t).argmin())
            (exact if abs(ts_t[k] - t) < 0.005 else interpo).append((s, k))
        print("帧总数 %d | 精确组(|Δt|<5ms) %d (%.2f%%) | 插值组 %d (%.2f%%)"
              % (len(stamps), len(exact), 100.*len(exact)/len(stamps),
                 len(interpo), 100.*len(interpo)/len(stamps)))
        def M(x, k):
            T = np.eye(4); T[:3, :3] = R_t[k]; T[:3, 3] = C_t[k]; return T
        legs = {}
        sb_step = a.stride_b or a.stride
        sa = exact[::a.stride]; sb = interpo[::sb_step]
        legs["A 精确 + traj 原值   "] = ([s for s, k in sa], [M(s, k) for s, k in sa])
        legs["B 插值 + slerp/lerp  "] = ([s for s, k in sb], [interp(float(s)) for s, k in sb])
        legs["C 插值帧 + 最近邻位姿"] = ([s for s, k in sb], [M(s, k) for s, k in sb])
        legs["D 插值帧 + 位姿写反  "] = ([s for s, k in sb], [(None if interp(float(s)) is None else np.linalg.inv(interp(float(s)))) for s, k in sb])
        for name, (ss, pp) in legs.items():
            keep = [(s, p) for s, p in zip(ss, pp) if p is not None]
            r, n = pose_leg(vd, vid, [s for s, _ in keep], [p for _, p in keep],
                            imgdir, depdir, intrdir, native, a.n)
            print("  %s 跨视中位|dz| = %.4f m   (n_frames=%d)" % (name, r, n))

    elif a.what == "depth":
        hs = sorted((ts_str(p) for p in glob.glob(os.path.join(vd, "highres_depth", "*.png"))), key=float)
        rows = []
        for s in hs[::max(1, len(hs)//60)]:
            d = cv2.imread(os.path.join(vd, "highres_depth", "%s_%s.png" % (vid, s)),
                           cv2.IMREAD_UNCHANGED).astype(np.float32)/1000.
            ar = resize_depth(d, "area"); ne = resize_depth(d, "nearest")
            # lowres 上采样 (v1 口径) 作对照
            lp = os.path.join(vd, "lowres_depth", "%s_%s.png" % (vid, s))
            lo = None
            if os.path.exists(lp):
                l = cv2.imread(lp, cv2.IMREAD_UNCHANGED).astype(np.float32)/1000.
                lo = cv2.resize(l, (W, H), interpolation=cv2.INTER_NEAREST)
            both = (ar > 0) & (ne > 0)
            fly = np.abs(ar[both] - ne[both]) > 0.05*ne[both]
            r = dict(v_native=float((d > 0).mean()), v_area=float((ar > 0).mean()),
                     v_near=float((ne > 0).mean()),
                     fly=float(fly.mean()),
                     uniq_native=len(np.unique(d[d > 0])), uniq_area=len(np.unique(ar[ar > 0])),
                     uniq_near=len(np.unique(ne[ne > 0])))
            if lo is not None:
                m = (ar > 0) & (lo > 0)
                r["dlow_med"] = float(np.median(np.abs(ar[m]-lo[m])))
                r["uniq_low"] = len(np.unique(lo[lo > 0]))
                # stage3->stage4 新增值 (blend.py 的多尺度监督)
                s3 = cv2.resize(lo, (W//2, H//2), interpolation=cv2.INTER_NEAREST)
                r["new_lo"] = len(np.unique(lo[lo > 0])) - len(np.unique(s3[s3 > 0]))
                s3a = cv2.resize(ar, (W//2, H//2), interpolation=cv2.INTER_NEAREST)
                r["new_ar"] = len(np.unique(ar[ar > 0])) - len(np.unique(s3a[s3a > 0]))
            rows.append(r)
        def med(k):
            v = [r[k] for r in rows if k in r]
            return float(np.median(v)) if v else float("nan")
        print("样本 %d 帧" % len(rows))
        print("  原生 1920x1440 有效率            中位 %.4f  (min %.4f)" % (med("v_native"), min(r["v_native"] for r in rows)))
        print("  768x576 有效率  area             中位 %.4f" % med("v_area"))
        print("  768x576 有效率  nearest          中位 %.4f" % med("v_near"))
        print("  area vs nearest 差 >5%% 的像素占比 中位 %.4f  (= 跨深度断崖的平均, 飞点)" % med("fly"))
        print("  768x576 不同深度值个数: FARO-area %.0f | FARO-near %.0f | LiDAR 上采样(v1) %.0f"
              % (med("uniq_area"), med("uniq_near"), med("uniq_low")))
        print("  stage3->stage4 新增深度值个数:   FARO-area %.0f | LiDAR 上采样(v1) %.0f"
              % (med("new_ar"), med("new_lo")))
        print("  FARO(area) 与 LiDAR 上采样 的中位差 %.4f m" % med("dlow_med"))

    elif a.what == "k3":
        hs = sorted((ts_str(p) for p in glob.glob(os.path.join(vd, "highres_depth", "*.png"))), key=float)
        vg = np.array(sorted(float(ts_str(p)) for p in glob.glob(os.path.join(vd, "vga_wide_intrinsics", "*.pincam"))))
        rat, dts = [], []
        for s in hs:
            wp = os.path.join(vd, "wide_intrinsics", "%s_%s.pincam" % (vid, s))
            if not os.path.exists(wp):
                continue
            Wp = np.loadtxt(wp)
            j = int(np.abs(vg - float(s)).argmin()); dts.append(abs(vg[j]-float(s)))
            vp = os.path.join(vd, "vga_wide_intrinsics", "%s_%.3f.pincam" % (vid, vg[j]))
            if not os.path.exists(vp):
                continue
            Vp = np.loadtxt(vp)
            rat.append(Wp[2:]/Vp[2:])
        r = np.array(rat)
        print("wide_intrinsics / vga_wide_intrinsics  (n=%d, 时间戳错开中位 %.4f s)" % (len(r), np.median(dts)))
        for i, nm in enumerate(["fx", "fy", "cx", "cy"]):
            print("  %s: 中位 %.6f  p1 %.6f  p99 %.6f" % (nm, np.median(r[:, i]),
                  np.percentile(r[:, i], 1), np.percentile(r[:, i], 99)))


if __name__ == "__main__":
    main()
