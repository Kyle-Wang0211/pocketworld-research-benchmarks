#!/usr/bin/env python3
"""shift-tolerant NCC:在 holdout 图上以 ±1.5cm 搜索窗取最佳 NCC。

动机:cut 带条带图显示大量假阴性来自"周期性结构(格栅/圆环/百叶)错开半个周期"
与小的配准误差 —— 内容其实是同一块表面。
但放宽搜索也会抬高零分布,所以必须在同一零分布(深度扰动 s=0.85/1.20)上重测 AUC,
用 AUC 判断它是不是更好的真值信号,而不是拍脑袋。
"""
import os
import numpy as np
from PIL import Image
import holdout_ncc as H

HERE = H.HERE
S_T = H.S_NCC          # 模板 32
S_SRC = 128            # holdout 提取 128x128,覆盖 2*side 物理范围
S_DN = 64              # 降采样后 64x64
CTRL = [0.85, 1.20]


def ncc_shift(tmpl, area):
    """tmpl SxS 已零均值单位方差; area MxM. 返回所有整数位移下的最大 NCC。"""
    S = tmpl.shape[0]; M = area.shape[0]; K = M - S + 1
    if K < 1:
        return np.nan
    # 积分图求每个窗口的均值/方差
    c = np.cumsum(np.cumsum(np.pad(area, ((1, 0), (1, 0))), 0), 1)
    c2 = np.cumsum(np.cumsum(np.pad(area ** 2, ((1, 0), (1, 0))), 0), 1)
    def box(cc):
        return cc[S:, S:] - cc[:-S, S:] - cc[S:, :-S] + cc[:-S, :-S]
    n = S * S
    s1 = box(c); s2 = box(c2)
    var = s2 / n - (s1 / n) ** 2
    std = np.sqrt(np.maximum(var, 0))
    # 互相关:直接 FFT 太重,K<=33 时暴力即可
    out = np.full((K, K), -2.0)
    for dy in range(K):
        for dx in range(K):
            if std[dy, dx] < 1e-3:
                continue
            w = area[dy:dy + S, dx:dx + S]
            out[dy, dx] = float((tmpl * (w - s1[dy, dx] / n)).mean() / std[dy, dx])
    return float(out.max()) if np.isfinite(out).any() else np.nan


def main():
    cams = H.read_cams(f"{H.MODEL}/cameras.bin")
    imgs = H.read_imgs(f"{H.MODEL}/images.bin")
    xyz, tracks = H.read_pts(f"{H.MODEL}/points3D.bin")
    idx = np.load(f"{HERE}/sample_idx.npy")
    d = np.load(f"{HERE}/holdout_ncc.npz", allow_pickle=True)

    path_of = {}
    for iid, im in imgs.items():
        k = int(im["name"].split("_")[1].split(".")[0])
        path_of[iid] = f"{H.PHOTOS}/{H.ORDER[k]}"
    all_ids = np.array(sorted(imgs))
    NS = len(idx); NC = len(CTRL)

    reqs = {}
    for slot, pi in enumerate(idx):
        P = xyz[pi]; T = list(tracks[pi])
        if len(T) < 2:
            continue
        Ct = np.stack([imgs[i]["C"] for i in T]); D = Ct - P
        Dn = D / np.linalg.norm(D, axis=1, keepdims=True)
        cm = Dn @ Dn.T; np.fill_diagonal(cm, 1.0)
        ref = T[int(np.argmax(np.degrees(np.arccos(np.clip(cm, -1, 1))).max(axis=1)))]
        ur, vr, zr = H.project(imgs[ref], cams[imgs[ref]["cid"]], P)
        if ur is None:
            continue
        reqs.setdefault(int(ref), []).append(
            (slot, -1, 0, ur, vr,
             float(np.clip(H.PATCH_M * cams[imgs[ref]["cid"]][0][0] / zr, H.PX_MIN, H.PX_MAX)), 1))
        dref = imgs[ref]["C"] - P; dref /= np.linalg.norm(dref)
        Tset = set(int(t) for t in T); cand = []
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
            dh = im["C"] - P; dh = dh / np.linalg.norm(dh)
            ang = np.degrees(np.arccos(np.clip(float(dref @ dh), -1, 1)))
            if H.ANG_MIN <= ang <= H.ANG_MAX:
                cand.append((ang, int(iid)))
        cand.sort()
        hold = [c[1] for c in cand[:H.N_HOLDOUT]]
        Cref = imgs[ref]["C"]
        for fi, Pp in [(0, P)] + [(1 + j, Cref + s * (P - Cref)) for j, s in enumerate(CTRL)]:
            for k, iid in enumerate(hold):
                im = imgs[iid]
                u, v, z = H.project(im, cams[im["cid"]], Pp)
                if u is None:
                    continue
                sp = float(np.clip(H.PATCH_M * cams[im["cid"]][0][0] / z, H.PX_MIN, H.PX_MAX))
                reqs.setdefault(int(iid), []).append((slot, fi, k, u, v, sp * 2.0, 2))

    P_ref = np.full((NS, H.S_EXT, H.S_EXT), np.nan, np.float32)
    A = np.full((NS, 1 + NC, H.N_HOLDOUT, S_DN, S_DN), np.nan, np.float32)
    for n, iid in enumerate(sorted(reqs)):
        gray = np.asarray(Image.open(path_of[iid]).convert("L"), dtype=np.float32)
        for (slot, fi, k, u, v, sp, kind) in reqs[iid]:
            if kind == 1:
                p = H.bilinear_patch(gray, u, v, sp, H.S_EXT)
                if p is not None:
                    P_ref[slot] = p
            else:
                p = H.bilinear_patch(gray, u, v, sp, S_SRC)
                if p is not None:
                    A[slot, fi, k] = p.reshape(S_DN, 2, S_DN, 2).mean(axis=(1, 3))
        if n % 40 == 0:
            print(f"  img {n}/{len(reqs)}", flush=True)

    res_med = np.full((NS, 1 + NC), np.nan)
    res_max = np.full((NS, 1 + NC), np.nan)
    for slot in range(NS):
        if not np.isfinite(P_ref[slot]).all():
            continue
        t = P_ref[slot].reshape(S_T, 2, S_T, 2).mean(axis=(1, 3))
        t = t - t.mean()
        if t.std() < 1e-3:
            continue
        t = t / t.std()
        for fi in range(1 + NC):
            vals = []
            for k in range(H.N_HOLDOUT):
                a = A[slot, fi, k]
                if not np.isfinite(a).all():
                    continue
                c = ncc_shift(t, a)
                if np.isfinite(c):
                    vals.append(c)
            if len(vals) >= 2:
                res_med[slot, fi] = float(np.median(vals))
                res_max[slot, fi] = max(vals)
        if slot % 60 == 0:
            print(f"  ncc {slot}/{NS}", flush=True)

    np.savez(f"{HERE}/holdout_shift.npz", idx=idx, ctrl=np.array(CTRL),
             shift_med=res_med, shift_max=res_max)

    def auc(pos, neg):
        pos = pos[np.isfinite(pos)]; neg = neg[np.isfinite(neg)]
        a = np.concatenate([pos, neg]); y = np.concatenate([np.ones(pos.size), np.zeros(neg.size)])
        o = np.argsort(a); r = np.empty(len(a)); r[o] = np.arange(1, len(a) + 1)
        return float((r[y == 1].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))

    c = np.load(f"{HERE}/holdout_control.npz")
    F = list(c["factors"]); cm_ = c["ncc_median_ctrl"]
    fixed_neg = np.concatenate([cm_[:, F.index(s)] for s in CTRL])
    shift_neg = np.concatenate([res_med[:, 1], res_med[:, 2]])

    def q(v, n):
        v = v[np.isfinite(v)]
        p = np.percentile(v, [5, 25, 50, 75, 90, 95])
        return (f"{n:>22s} n={v.size:4d} p5={p[0]:+.3f} p25={p[1]:+.3f} p50={p[2]:+.3f} "
                f"p75={p[3]:+.3f} p90={p[4]:+.3f} p95={p[5]:+.3f}")

    print("\n=== 固定位置 NCC(基准) ===")
    print(q(d["ncc_median"], "REAL median"))
    print(q(fixed_neg, "NULL(s=.85/1.2) median"))
    print(f"  AUC = {auc(d['ncc_median'], fixed_neg):.3f}")
    print("\n=== shift-tolerant NCC(±1.5cm 搜索) ===")
    print(q(res_med[:, 0], "REAL median"))
    print(q(shift_neg, "NULL(s=.85/1.2) median"))
    print(f"  AUC = {auc(res_med[:, 0], shift_neg):.3f}")
    print(q(res_max[:, 0], "REAL max"))
    print(q(np.concatenate([res_max[:, 1], res_max[:, 2]]), "NULL max"))
    print(f"  AUC(max) = {auc(res_max[:,0], np.concatenate([res_max[:,1], res_max[:,2]])):.3f}")

    r = res_med[:, 0]; ok = np.isfinite(r) & np.isfinite(d["ncc_median"])
    lift = r[ok] - d["ncc_median"][ok]
    print(f"\n  shift 提升(real): p50={np.median(lift):+.3f} p90={np.percentile(lift,90):+.3f}")
    ln = shift_neg[np.isfinite(shift_neg)]; lf = fixed_neg[np.isfinite(fixed_neg)]
    print(f"  shift 提升(null): p50={np.median(ln)-np.median(lf):+.3f}")


if __name__ == "__main__":
    main()
