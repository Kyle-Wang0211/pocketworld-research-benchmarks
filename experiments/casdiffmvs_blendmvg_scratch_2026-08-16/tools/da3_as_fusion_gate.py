#!/usr/bin/env python3
"""DA3 单目深度当**融合门的额外判据**能不能用。

  python3.11 da3_as_fusion_gate.py --fixture .../fx_official --pred .../OFFICIAL \
      --cap .../phone_cap_20260811 --da3 .../da3_probe/da3_504.npz

🔴 为什么不能直接"加上门再看 RMS":07-31 报告的教训 ——
   **纯过滤器只删点、从不移动任何点,所以任何精度改善 100% 是幸存者效应。**
   要证明一个门有用,必须在**同等保留率**下与已有判据对比。

本脚本回答三个逐级递进的问题:

  ① **有没有预测力**:在官方门的幸存像素里,DA3 分歧度与 MVS 误差(对稀疏点)
     的相关性。若约等于 0,这条路当场判死。
  ② **是不是新信息**:DA3 分歧度与**几何认同视图数**的相关性。
     08-07 测过单目残差与视差角正交(Spearman −0.17/−0.24)——
     若与几何判据高度相关,那它只是把几何已知的事重说一遍,加了也没用。
  ③ **同等保留率下谁更强**:删掉同样比例的点,用 DA3 删 vs 用几何门收紧删,
     比幸存者的 `<1%`。**这才是判决。**

⚠️ DA3 必须逐帧标定(裸米制 p50 误差 12%)。用稳健单尺度(实测 scale 与
   scale+shift 几乎等效,且 scale 的 p90 更好),标定靶用**稀疏点**而非 MVS 深度 ——
   拿 MVS 标定会让两者按构造对齐,把要测的东西抹掉。
"""
import argparse, json, os
import numpy as np
from scipy.stats import spearmanr


def read_ply(p):
    f = open(p, "rb"); n = None
    while True:
        l = f.readline()
        if l.startswith(b"element vertex"): n = int(l.split()[-1])
        if l.strip() == b"end_header": break
    d = np.frombuffer(f.read(n * 15), dtype=np.dtype(
        [("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
         ("r", "u1"), ("g", "u1"), ("b", "u1")]), count=n)
    return np.stack([d["x"], d["y"], d["z"]], 1).astype(np.float64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--cap", required=True)
    ap.add_argument("--da3", required=True)
    ap.add_argument("--photo-thres", type=float, nargs=3, default=[0.3, 0.5, 0.5])
    args = ap.parse_args()

    FX = args.fixture
    meta = json.load(open(f"{FX}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    CM = np.fromfile(f"{FX}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{FX}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])
    P = read_ply(f"{args.cap}/official_sfm_sparse.ply")
    Z = np.load(args.da3)
    sh = Z["0"].shape
    sc0 = json.load(open(f"{args.cap}/sidecars/{meta['names'][0].replace('.jpg','.json')}"))
    f_proc = sc0["intrinsics_fxfycxcy"][0] * (sh[1] / sc0["image_w"])

    def cam(f):
        return (CM[f, 0:9].reshape(3, 3).astype(np.float64),
                CM[f, 9:18].reshape(3, 3).astype(np.float64),
                CM[f, 18:21].astype(np.float64))

    # NEAR3 可见性(与其它脚本同口径)
    Cc = np.stack([-(CM[i, 9:18].reshape(3, 3).astype(np.float64).T
                     @ CM[i, 18:21].astype(np.float64)) for i in range(NF)])
    near3 = np.argsort(((P[:, None, :] - Cc[None]) ** 2).sum(2), 1)[:, :3]
    vis3 = np.zeros((len(P), NF), bool)
    np.put_along_axis(vis3, near3, True, 1)

    yy, xx = np.mgrid[0:H, 0:W]
    uv1 = np.stack([xx, yy, np.ones((H, W))], -1).reshape(-1, 3)
    D = [np.load(f"{args.pred}/depth/{f:04d}.npy").astype(np.float64) for f in range(NF)]
    CF = [[np.load(f"{args.pred}/conf{k}/{f:04d}.npy") for f in range(NF)] for k in range(3)]

    rows = []          # (mvs相对误差, DA3分歧度, 几何认同数)
    for f in range(NF):
        Kr, Rr, tr = cam(f)
        dr = D[f]
        # ── 官方门 ──
        photo = np.ones_like(dr, bool)
        for k in range(3):
            photo &= (CF[k][f] > args.photo_thres[k])
        Xw = ((uv1 @ np.linalg.inv(Kr).T) * dr.reshape(-1, 1) - tr) @ Rr
        agree = np.zeros(H * W, np.int32)
        for s in NB[f]:
            Ks, Rs, ts = cam(int(s))
            Xs = Xw @ Rs.T + ts
            zs = Xs[:, 2]; ok = zs > 1e-6
            pr = np.zeros((H * W, 2))
            pr[ok] = (Xs[ok] @ Ks.T)[:, :2] / zs[ok, None]
            us = np.where(ok, np.round(pr[:, 0]), -1)
            vs = np.where(ok, np.round(pr[:, 1]), -1)
            inb = ok & (us >= 0) & (us < W) & (vs >= 0) & (vs < H)
            idx = np.flatnonzero(inb)
            if not idx.size: continue
            ds = D[int(s)][vs[idx].astype(int), us[idx].astype(int)]
            Xcs = (np.stack([us[idx], vs[idx], np.ones(idx.size)], -1)
                   @ np.linalg.inv(Ks).T) * ds[:, None]
            Xrb = ((Xcs - ts) @ Rs) @ Rr.T + tr
            zrb = Xrb[:, 2]; g = zrb > 1e-6
            uvb = np.full((idx.size, 2), 1e9)
            uvb[g] = (Xrb[g] @ Kr.T)[:, :2] / zrb[g, None]
            hit = g & (np.hypot(uvb[:, 0] - xx.ravel()[idx], uvb[:, 1] - yy.ravel()[idx]) < 1.0) \
                & (np.abs(zrb - dr.ravel()[idx]) / np.maximum(dr.ravel()[idx], 1e-6) < 0.01)
            agree[idx[hit]] += 1
        survive = (photo.ravel() & (agree >= 3))

        # ── DA3:用**稀疏点**标定单尺度,再算逐像素分歧度 ──
        da = Z[str(f)].astype(np.float64) * f_proc / 300.0
        da_full = np.repeat(np.repeat(da, int(np.ceil(H / sh[0])), 0),
                            int(np.ceil(W / sh[1])), 1)[:H, :W]
        if da_full.shape != dr.shape:      # 尺寸兜底:最近邻重采样
            yi = (np.arange(H) * sh[0] // H).clip(0, sh[0] - 1)
            xi = (np.arange(W) * sh[1] // W).clip(0, sh[1] - 1)
            da_full = da[np.ix_(yi, xi)]
        Xc = P @ Rr.T + tr
        z = Xc[:, 2]; ok = z > 1e-6
        uv = (Xc[ok] @ Kr.T)[:, :2] / z[ok, None]
        us = np.round(uv[:, 0]).astype(int); vs = np.round(uv[:, 1]).astype(int)
        msk = (us >= 0) & (us < W) & (vs >= 0) & (vs < H) & vis3[np.flatnonzero(ok), f]
        if msk.sum() < 50:
            continue
        gt = z[ok][msk]
        d_da = da_full[vs[msk], us[msk]]
        good = d_da > 1e-6
        if good.sum() < 50: continue
        scale = np.median(gt[good] / d_da[good])          # 稳健单尺度,靶=稀疏点
        da_cal = da_full * scale
        disagree = np.abs(dr - da_cal) / np.maximum(dr, 1e-6)

        # 在稀疏点位置上取三元组
        lin = vs[msk] * W + us[msk]
        sv = survive[lin]
        if sv.sum() < 20: continue
        e_mvs = np.abs(dr.ravel()[lin] - gt) / gt
        rows.append(np.stack([e_mvs[sv], disagree.ravel()[lin][sv],
                              agree[lin][sv].astype(float)], 1))

    A = np.concatenate(rows)
    print(f"官方门幸存 × 稀疏点观测 {len(A):,}(共 {len(rows)} 帧)\n")

    print("══ ① DA3 分歧度有没有预测力 ══")
    r1 = spearmanr(A[:, 1], A[:, 0]).statistic
    print(f"  Spearman(DA3分歧度, MVS误差) = {r1:+.4f}")
    print(f"  ⇒ {'有预测力' if abs(r1) > 0.10 else '🔴 几乎无预测力,这条路判死'}")

    print("\n══ ② 是不是几何判据不知道的新信息 ══")
    r2 = spearmanr(A[:, 2], A[:, 0]).statistic
    r3 = spearmanr(A[:, 1], A[:, 2]).statistic
    print(f"  Spearman(几何认同数, MVS误差)  = {r2:+.4f}   ← 已有判据的预测力")
    print(f"  Spearman(DA3分歧度, 几何认同数) = {r3:+.4f}   ← 两者相关性")
    print(f"  ⇒ {'正交,带来新信息' if abs(r3) < 0.3 else '与几何高度相关,信息重复'}")

    print("\n══ ③ 同等保留率下谁更强(判决)══")
    print(f"{'保留率':>8}{'DA3门 <1%':>12}{'几何门收紧 <1%':>16}{'随机基线':>10}")
    for keep in (0.95, 0.90, 0.80, 0.70):
        n = int(len(A) * keep)
        i_da = np.argsort(A[:, 1])[:n]                      # 分歧最小的 n 个
        i_ge = np.argsort(-A[:, 2], kind="stable")[:n]      # 认同最多的 n 个
        f_da = 100 * (A[i_da, 0] < .01).mean()
        f_ge = 100 * (A[i_ge, 0] < .01).mean()
        base = 100 * (A[:, 0] < .01).mean()
        print(f"{100*keep:7.0f}%{f_da:11.2f}%{f_ge:15.2f}%{base:9.2f}%")
    print("\n  ⇒ 若 DA3 门那一列**高于**几何门收紧,说明它删对了几何删不掉的点")


if __name__ == "__main__":
    main()
