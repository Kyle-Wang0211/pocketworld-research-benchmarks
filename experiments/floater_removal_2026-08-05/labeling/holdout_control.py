#!/usr/bin/env python3
"""留出视角 NCC 的零假设标定(negative control)。

控制组构造:把 P 沿 ref 相机视线平移到 P' = C_ref + s*(P - C_ref)。
=> ref 视图里投影像素完全不变(ref patch 逐字节相同),只有深度错。
这正是"低视差深度歧义浮点"的失效模式。s != 1 的 NCC 分布 = 浮点应有的分布。
另加 s=1 但换成"别的采样点的 3D 位置"的完全随机零分布。

同时统计 ref patch 对比度(纹理量),用于诊断 NCC 的失败模式。
不参与真值判定,仅用于给主会话标定阈值。
"""
import os, json
import numpy as np
from PIL import Image

import holdout_ncc as H

HERE = H.HERE
FACTORS = [0.70, 0.85, 0.90, 1.10, 1.20, 1.40]


def main():
    cams = H.read_cams(f"{H.MODEL}/cameras.bin")
    imgs = H.read_imgs(f"{H.MODEL}/images.bin")
    xyz, tracks = H.read_pts(f"{H.MODEL}/points3D.bin")
    idx = np.load(f"{HERE}/sample_idx.npy")
    d = np.load(f"{HERE}/holdout_ncc.npz", allow_pickle=True)
    ncc_med_real = d["ncc_median"]

    path_of = {}
    for iid, im in imgs.items():
        k = int(im["name"].split("_")[1].split(".")[0])
        path_of[iid] = f"{H.PHOTOS}/{H.ORDER[k]}"
    all_ids = np.array(sorted(imgs))

    NS = len(idx)
    NF = len(FACTORS)
    rng = np.random.default_rng(7)
    perm = rng.permutation(NS)          # 随机零分布:借用别的点的位置

    reqs = {}
    hold_of = [[] for _ in range(NS)]
    ref_of = [None] * NS
    for slot, pi in enumerate(idx):
        P = xyz[pi]
        T = list(tracks[pi])
        if len(T) < 2:
            continue
        Ct = np.stack([imgs[i]["C"] for i in T])
        D = Ct - P
        Dn = D / np.linalg.norm(D, axis=1, keepdims=True)
        cosm = Dn @ Dn.T
        np.fill_diagonal(cosm, 1.0)
        ref = T[int(np.argmax(np.degrees(np.arccos(np.clip(cosm, -1, 1))).max(axis=1)))]
        ur, vr, zr = H.project(imgs[ref], cams[imgs[ref]["cid"]], P)
        if ur is None:
            continue
        ref_of[slot] = int(ref)
        reqs.setdefault(int(ref), []).append(
            (slot, -1, 0, ur, vr, float(np.clip(H.PATCH_M * cams[imgs[ref]["cid"]][0][0] / zr,
                                                H.PX_MIN, H.PX_MAX))))
        dref = imgs[ref]["C"] - P
        dref = dref / np.linalg.norm(dref)
        Tset = set(int(t) for t in T)
        cand = []
        for iid in all_ids:
            if int(iid) in Tset:
                continue
            im = imgs[iid]
            dist = float(np.linalg.norm(im["C"] - P))
            if not (H.DIST_MIN <= dist <= H.DIST_MAX):
                continue
            u, v, z = H.project(im, cams[im["cid"]], P)
            if u is None:
                continue
            W, Hh = cams[im["cid"]][1], cams[im["cid"]][2]
            if not (H.MARGIN_PX <= u <= W - H.MARGIN_PX and H.MARGIN_PX <= v <= Hh - H.MARGIN_PX):
                continue
            dh = im["C"] - P
            dh = dh / np.linalg.norm(dh)
            ang = np.degrees(np.arccos(np.clip(float(dref @ dh), -1, 1)))
            if not (H.ANG_MIN <= ang <= H.ANG_MAX):
                continue
            cand.append((ang, int(iid)))
        cand.sort()
        hold_of[slot] = [c[1] for c in cand[:H.N_HOLDOUT]]

        Cref = imgs[ref]["C"]
        # 各扰动因子 + 随机零分布(fi = NF)
        targets = [(fi, Cref + s * (P - Cref)) for fi, s in enumerate(FACTORS)]
        targets.append((NF, xyz[idx[perm[slot]]]))
        for fi, Pp in targets:
            for k, iid in enumerate(hold_of[slot]):
                im = imgs[iid]
                u, v, z = H.project(im, cams[im["cid"]], Pp)
                if u is None:
                    continue
                W, Hh = cams[im["cid"]][1], cams[im["cid"]][2]
                if not (H.MARGIN_PX <= u <= W - H.MARGIN_PX and H.MARGIN_PX <= v <= Hh - H.MARGIN_PX):
                    continue
                sp = float(np.clip(H.PATCH_M * cams[im["cid"]][0][0] / z, H.PX_MIN, H.PX_MAX))
                reqs.setdefault(int(iid), []).append((slot, fi, k, u, v, sp))

    S = H.S_EXT
    P_ref = np.full((NS, S, S), np.nan, np.float32)
    P_p = np.full((NS, NF + 1, H.N_HOLDOUT, S, S), np.nan, np.float32)
    for n, iid in enumerate(sorted(reqs)):
        gray = np.asarray(Image.open(path_of[iid]).convert("L"), dtype=np.float32)
        for (slot, fi, k, u, v, sp) in reqs[iid]:
            p = H.bilinear_patch(gray, u, v, sp, S)
            if p is None:
                continue
            if fi < 0:
                P_ref[slot] = p
            else:
                P_p[slot, fi, k] = p
        if n % 40 == 0:
            print(f"  img {n}/{len(reqs)}", flush=True)

    def norm(p):
        q = p.reshape(H.S_NCC, 2, H.S_NCC, 2).mean(axis=(1, 3))
        q = q - q.mean()
        s = q.std()
        return None if s < 1e-3 else q / s

    med = np.full((NS, NF + 1), np.nan)
    mx = np.full((NS, NF + 1), np.nan)
    ref_std = np.full(NS, np.nan)
    for slot in range(NS):
        if not np.isfinite(P_ref[slot]).all():
            continue
        a = norm(P_ref[slot])
        if a is None:
            continue
        ref_std[slot] = float(P_ref[slot].reshape(H.S_NCC, 2, H.S_NCC, 2).mean(axis=(1, 3)).std())
        for fi in range(NF + 1):
            vals = []
            for k in range(H.N_HOLDOUT):
                b = P_p[slot, fi, k]
                if not np.isfinite(b).all():
                    continue
                b = norm(b)
                if b is None:
                    continue
                vals.append(float((a * b).mean()))
            if len(vals) >= 2:
                med[slot, fi] = float(np.median(vals))
                mx[slot, fi] = max(vals)

    np.savez(f"{HERE}/holdout_control.npz", idx=idx, factors=np.array(FACTORS),
             ncc_median_ctrl=med, ncc_max_ctrl=mx, ref_std=ref_std)

    def pr(name, v):
        v = v[np.isfinite(v)]
        q = np.percentile(v, [5, 25, 50, 75, 95])
        return (f"{name:>14s} n={v.size:3d} p5={q[0]:+.3f} p25={q[1]:+.3f} "
                f"p50={q[2]:+.3f} p75={q[3]:+.3f} p95={q[4]:+.3f}")

    print("\n=== 零假设标定:ncc_median ===")
    print(pr("REAL(s=1.00)", ncc_med_real))
    for fi, s in enumerate(FACTORS):
        print(pr(f"s={s:.2f}", med[:, fi]))
    print(pr("random-pt", med[:, NF]))
    print("\n=== 零假设标定:ncc_max ===")
    print(pr("REAL(s=1.00)", np.load(f'{HERE}/holdout_ncc.npz')["ncc_max"]))
    for fi, s in enumerate(FACTORS):
        print(pr(f"s={s:.2f}", mx[:, fi]))
    print(pr("random-pt", mx[:, NF]))

    # 阈值扫描:以 s=0.85/1.20 与 random 作为"浮点"代理,真实点作为"正类"
    real = ncc_med_real[np.isfinite(ncc_med_real)]
    for label, col in [("s=0.85", 1), ("s=1.20", 4), ("random", NF)]:
        neg = med[:, col][np.isfinite(med[:, col])]
        print(f"\n--- 阈值扫描 vs {label} (ncc_median) ---")
        print("  thr   keep_real%  keep_neg%(=漏)")
        for thr in [0.0, 0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7]:
            print(f"  {thr:.2f}   {100*(real>=thr).mean():6.1f}      {100*(neg>=thr).mean():6.1f}")
        # AUC(真实 vs 该零分布)
        a = np.concatenate([real, neg])
        y = np.concatenate([np.ones(real.size), np.zeros(neg.size)])
        o = np.argsort(a)
        r = np.empty(len(a)); r[o] = np.arange(1, len(a) + 1)
        auc = (r[y == 1].sum() - real.size * (real.size + 1) / 2) / (real.size * neg.size)
        print(f"  separability AUC(real vs {label}) = {auc:.3f}")

    # 纹理量 vs NCC(失败模式诊断)
    ok = np.isfinite(ncc_med_real) & np.isfinite(ref_std)
    qs = np.percentile(ref_std[ok], [25, 50, 75])
    print("\n=== 失败模式诊断:ref patch 对比度(灰度 std)分箱 ===")
    print(f" ref_std 分位: p25={qs[0]:.1f} p50={qs[1]:.1f} p75={qs[2]:.1f}")
    bins = [(-1, qs[0]), (qs[0], qs[1]), (qs[1], qs[2]), (qs[2], 1e9)]
    for lo, hi in bins:
        m = ok & (ref_std > lo) & (ref_std <= hi)
        mn = ok & (ref_std > lo) & (ref_std <= hi)
        nm = med[:, NF]
        print(f"  std({lo:6.1f},{hi:7.1f}] n={m.sum():3d} "
              f"real_med={np.median(ncc_med_real[m]):+.3f} "
              f"random_med={np.nanmedian(nm[mn]):+.3f}")


if __name__ == "__main__":
    main()
