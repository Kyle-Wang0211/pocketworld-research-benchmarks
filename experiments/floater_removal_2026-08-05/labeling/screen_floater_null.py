#!/usr/bin/env python3
"""远景(12cm)NCC 的零假设标定 —— 防止重蹈 shift-tolerant 的覆辙。

12cm patch 视野更大、低频成分更多,可能"天生"就更相关。
所以远景 NCC 的高值到底有没有意义,必须在同一深度扰动零分布上重测。
"""
import os
import numpy as np
from PIL import Image
import holdout_ncc as H
import screen_floater as SF

HERE = H.HERE
CTRL = [0.85, 1.20]


def main():
    cams = H.read_cams(f"{H.MODEL}/cameras.bin")
    imgs = H.read_imgs(f"{H.MODEL}/images.bin")
    xyz, tracks = H.read_pts(f"{H.MODEL}/points3D.bin")
    idx = np.load(f"{HERE}/sample_idx.npy")
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
        fxr = cams[imgs[ref]["cid"]][0][0]
        reqs.setdefault(int(ref), []).append(
            (slot, -1, 0, ur, vr, float(np.clip(SF.FAR_M * fxr / zr, SF.FAR_PX_MIN, SF.FAR_PX_MAX))))
        dref = imgs[ref]["C"] - P; dref /= np.linalg.norm(dref)
        Tset = set(int(t) for t in T); cand = []
        for iid in all_ids:
            if int(iid) in Tset:
                continue
            im = imgs[iid]
            if not (H.DIST_MIN <= float(np.linalg.norm(im["C"] - P)) <= H.DIST_MAX):
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
                fx = cams[im["cid"]][0][0]
                reqs.setdefault(int(iid), []).append(
                    (slot, fi, k, u, v,
                     float(np.clip(SF.FAR_M * fx / z, SF.FAR_PX_MIN, SF.FAR_PX_MAX))))

    S = SF.S_FAR_EXT
    RF = np.full((NS, S, S), np.nan, np.float32)
    HFa = np.full((NS, 1 + NC, H.N_HOLDOUT, S, S), np.nan, np.float32)
    for n, iid in enumerate(sorted(reqs)):
        gray = np.asarray(Image.open(path_of[iid]).convert("L"), dtype=np.float32)
        for (slot, fi, k, u, v, sp) in reqs[iid]:
            p = H.bilinear_patch(gray, u, v, sp, S)
            if p is None:
                continue
            if fi < 0:
                RF[slot] = p
            else:
                HFa[slot, fi, k] = p
        if n % 40 == 0:
            print(f"  img {n}/{len(reqs)}", flush=True)

    SN = SF.S_FAR_NCC

    def norm(p):
        q = p.reshape(SN, S // SN, SN, S // SN).mean(axis=(1, 3))
        q = q - q.mean(); s = q.std()
        return None if s < 1e-3 else q / s

    med = np.full((NS, 1 + NC), np.nan)
    mxx = np.full((NS, 1 + NC), np.nan)
    for slot in range(NS):
        if not np.isfinite(RF[slot]).all():
            continue
        a = norm(RF[slot])
        if a is None:
            continue
        for fi in range(1 + NC):
            vals = []
            for k in range(H.N_HOLDOUT):
                b = HFa[slot, fi, k]
                if not np.isfinite(b).all():
                    continue
                b = norm(b)
                if b is None:
                    continue
                vals.append(float((a * b).mean()))
            if len(vals) >= 2:
                med[slot, fi] = float(np.median(vals)); mxx[slot, fi] = max(vals)

    np.savez(f"{HERE}/screen_floater_null.npz", idx=idx, ctrl=np.array(CTRL),
             far_med=med, far_max=mxx)

    d = np.load(f"{HERE}/holdout_ncc.npz", allow_pickle=True)
    c = np.load(f"{HERE}/holdout_control.npz")
    F = list(c["factors"])
    near_neg = np.concatenate([c["ncc_median_ctrl"][:, F.index(s)] for s in CTRL])
    far_neg = np.concatenate([med[:, 1], med[:, 2]])

    def auc(pos, neg):
        pos = pos[np.isfinite(pos)]; neg = neg[np.isfinite(neg)]
        a = np.concatenate([pos, neg]); y = np.concatenate([np.ones(pos.size), np.zeros(neg.size)])
        o = np.argsort(a); r = np.empty(len(a)); r[o] = np.arange(1, len(a) + 1)
        return float((r[y == 1].sum() - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size))

    def q(v, n):
        v = v[np.isfinite(v)]
        p = np.percentile(v, [5, 25, 50, 75, 90, 95])
        return (f"{n:>26s} n={v.size:4d} p5={p[0]:+.3f} p25={p[1]:+.3f} p50={p[2]:+.3f} "
                f"p75={p[3]:+.3f} p90={p[4]:+.3f} p95={p[5]:+.3f}")

    print("\n=== 近景 3cm(基准) ===")
    print(q(d["ncc_median"], "REAL"));  print(q(near_neg, "NULL(s=.85/1.2)"))
    print(f"  AUC = {auc(d['ncc_median'], near_neg):.3f}")
    print("\n=== 远景 12cm ===")
    print(q(med[:, 0], "REAL"));  print(q(far_neg, "NULL(s=.85/1.2)"))
    print(f"  AUC = {auc(med[:, 0], far_neg):.3f}")

    # 关键:浮点桶 50 点的远景值,要对照远景零分布的分位数来读
    fs = np.load(f"{HERE}/screen_floater_far.npz")
    fv = fs["ncc_median_far"]; fv = fv[np.isfinite(fv)]
    fn = far_neg[np.isfinite(far_neg)]
    print(f"\n=== 浮点桶 50 点的远景 NCC,按远景零分布分位数定位 ===")
    print(f"  远景零分布: p50={np.percentile(fn,50):+.3f} p75={np.percentile(fn,75):+.3f} "
          f"p90={np.percentile(fn,90):+.3f} p95={np.percentile(fn,95):+.3f}")
    for t, nm in [(np.percentile(fn, 75), "零分布p75"), (np.percentile(fn, 90), "零分布p90"),
                  (np.percentile(fn, 95), "零分布p95")]:
        print(f"  far_med > {nm}({t:+.3f}): {int((fv>t).sum()):2d}/{len(fv)} "
              f"({100*(fv>t).mean():.0f}%)")


if __name__ == "__main__":
    main()
