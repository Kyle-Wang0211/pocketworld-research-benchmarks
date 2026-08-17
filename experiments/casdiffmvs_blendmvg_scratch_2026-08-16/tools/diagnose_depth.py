#!/usr/bin/env python3
"""深度图质量诊断 —— 回答"侧面那堆扇形薄片是缺融合,还是深度图本身坏"。

三件互相独立的事,任何一件都能单独定罪:

  ① **深度范围贴边率**:多少像素被压在 dmin/dmax 上。
     贴边 = 网络"不知道",被范围截断 ⇒ 这些点会在视线方向拉成薄片。

  ② **几何一致性**(标准 MVS 滤波的判据,也是最好的诊断)
     参考帧像素 p 深度 d → 投到源视图 → 取源视图那里的深度 → 反投回世界 → 再投回参考帧。
     若深度正确,应该回到 p 附近且深度相符。
     记录:重投影误差 < 1px 且 相对深度差 < 1% 的源视图个数(0..4)。
     🔑 **这个判据对无纹理区同样有效** —— 不像稀疏点指标那样看不见白墙地板。

  ③ **置信度是否有区分力**:conf 与几何一致性的关系。
     若 conf 高的像素几何上也一致,说明 conf 能用来滤;若无关,说明 conf 是坏的旋钮。

⚠️ 只诊断不修改。修法(融合/滤波)另说,先知道病在哪。
"""
import argparse, json, os
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--frames", type=int, default=0, help="只看前 N 帧,0=全部")
    args = ap.parse_args()

    FX = args.fixture
    meta = json.load(open(f"{FX}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    CM = np.fromfile(f"{FX}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{FX}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])
    n = args.frames or NF

    D = [np.load(f"{args.pred}/depth/{f:04d}.npy") for f in range(NF)]
    C = [np.load(f"{args.pred}/conf/{f:04d}.npy") for f in range(NF)]

    def cam(f):
        K = CM[f, 0:9].reshape(3, 3).astype(np.float64)
        R = CM[f, 9:18].reshape(3, 3).astype(np.float64)
        t = CM[f, 18:21].astype(np.float64)
        return K, R, t

    # ── ① 贴边率 ──
    lo_hit = hi_hit = tot = 0
    for f in range(n):
        d, lo, hi = D[f], CM[f, 24], CM[f, 25]
        lo_hit += int((d <= lo * 1.001).sum())
        hi_hit += int((d >= hi * 0.999).sum())
        tot += d.size
    print("══ ① 深度范围贴边率 ══")
    print(f"  压在 dmin 上 {100*lo_hit/tot:6.2f}%   压在 dmax 上 {100*hi_hit/tot:6.2f}%"
          f"   合计 {100*(lo_hit+hi_hit)/tot:6.2f}%")
    print("  (贴边=网络没定下来被范围截断,这些点会沿视线拉成薄片)")

    # ── ② 几何一致性 ──
    yy, xx = np.mgrid[0:H, 0:W]
    ones = np.ones((H, W))
    NS = meta["num_src"]          # 🔴 不写死 5:num_view 5→7 时源视图有 6 个
    nviews_hist = np.zeros(NS + 1, np.int64)
    conf_by_nv = [[] for _ in range(NS + 1)]
    for f in range(n):
        Kr, Rr, tr = cam(f)
        dr = D[f].astype(np.float64)
        uv1 = np.stack([xx, yy, ones], -1).reshape(-1, 3)
        Xc = (uv1 @ np.linalg.inv(Kr).T) * dr.reshape(-1, 1)
        Xw = (Xc - tr) @ Rr                                   # 世界坐标
        agree = np.zeros(H * W, np.int32)
        for s in NB[f]:
            Ks, Rs, ts = cam(int(s))
            Xs = Xw @ Rs.T + ts
            zs = Xs[:, 2]
            ok = zs > 1e-6
            uvs = np.full((H * W, 2), -1.0)
            uvs[ok] = (Xs[ok] @ Ks.T)[:, :2] / zs[ok, None]
            us = np.round(uvs[:, 0]).astype(int)
            vs = np.round(uvs[:, 1]).astype(int)
            inb = ok & (us >= 0) & (us < W) & (vs >= 0) & (vs < H)
            if inb.sum() == 0:
                continue
            ds = D[int(s)][vs[inb], us[inb]].astype(np.float64)   # 源视图自己估的深度
            # 用源视图的深度反投回世界,再投回参考帧
            uv1s = np.stack([us[inb], vs[inb], np.ones(inb.sum())], -1)
            Xcs = (uv1s @ np.linalg.inv(Ks).T) * ds[:, None]
            Xws = (Xcs - ts) @ Rs
            Xrb = Xws @ Rr.T + tr
            zrb = Xrb[:, 2]
            good = zrb > 1e-6
            uvb = np.full((inb.sum(), 2), 1e9)
            uvb[good] = (Xrb[good] @ Kr.T)[:, :2] / zrb[good, None]
            idx = np.flatnonzero(inb)
            reproj = np.hypot(uvb[:, 0] - xx.ravel()[idx], uvb[:, 1] - yy.ravel()[idx])
            ddiff = np.abs(zrb - dr.ravel()[idx]) / np.maximum(dr.ravel()[idx], 1e-6)
            hit = good & (reproj < 1.0) & (ddiff < 0.01)
            agree[idx[hit]] += 1
        nviews_hist += np.bincount(agree, minlength=NS + 1)
        cf = C[f].ravel()
        for k in range(NS + 1):
            m = agree == k
            if m.any():
                conf_by_nv[k].append(cf[m])

    tot2 = nviews_hist.sum()
    print("\n══ ② 几何一致性(重投影<1px 且 深度差<1% 的源视图个数)══")
    print("  🔑 这个判据对白墙/地板同样有效,不像稀疏点指标那样是瞎的")
    for k in range(NS + 1):
        bar = "█" * int(60 * nviews_hist[k] / tot2)
        print(f"  {k} 个视图认同  {100*nviews_hist[k]/tot2:6.2f}%  {bar}")
    print(f"\n  ⇒ **零个视图认同的像素占 {100*nviews_hist[0]/tot2:.2f}%** —— 这些就是薄片的来源")
    print(f"  ⇒ 标准 MVS 滤波要求 ≥2 个视图认同,能留下 "
          f"{100*nviews_hist[2:].sum()/tot2:.2f}%")

    print("\n══ ③ 置信度有没有区分力 ══")
    print(f"  {'认同视图数':<12}{'中位 conf':>10}{'p25':>9}{'p75':>9}")
    for k in range(NS + 1):
        if conf_by_nv[k]:
            c = np.concatenate(conf_by_nv[k])
            print(f"  {k:<12}{np.median(c):10.4f}{np.percentile(c,25):9.4f}"
                  f"{np.percentile(c,75):9.4f}")
    c0 = np.concatenate(conf_by_nv[0]) if conf_by_nv[0] else np.array([0.])
    c4 = np.concatenate(conf_by_nv[NS]) if conf_by_nv[NS] else np.array([0.])
    print(f"\n  0 认同 vs 全认同 的 conf 中位差 {np.median(c4)-np.median(c0):+.4f}")
    print(f"  ⇒ {'conf 有区分力,可以当滤波旋钮' if np.median(c4)-np.median(c0) > 0.1 else '🔴 conf 区分力弱,单靠 conf≥0.5 滤不掉薄片 —— 这正是当前 PLY 的做法'}")
    print(f"\n  当前 PLY 用的 conf≥0.5 能留下 "
          f"{100*np.mean(np.concatenate([np.concatenate(v) for v in conf_by_nv if v])>=0.5):.1f}% 的像素")

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        from PIL import Image
        for f in [0, n // 3, 2 * n // 3]:
            d, lo, hi = D[f], CM[f, 24], CM[f, 25]
            img = np.clip((d - lo) / (hi - lo), 0, 1)
            Image.fromarray((img * 255).astype(np.uint8)).save(f"{args.out}/depth_{f:04d}.png")
            Image.fromarray((np.clip(C[f], 0, 1) * 255).astype(np.uint8)).save(
                f"{args.out}/conf_{f:04d}.png")
        print(f"\n深度/置信度可视化 → {args.out}/")


if __name__ == "__main__":
    main()
