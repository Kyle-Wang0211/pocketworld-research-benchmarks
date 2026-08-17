#!/usr/bin/env python3
"""DA3METRIC-LARGE 在 97 帧真机 fixture 上对 SfM 点的误差分布。

回答的**不是**"DA3 准不准",而是一个很具体的工程问题:

  **能不能用它当 CasDiffMVS 逐像素深度范围的中心?**

因为今天实测过:整帧共用一个范围时,收紧就必然截断(ARM_T 贴边率 0.05%→0.27%
且几何一致性变差)。逐像素先验没有这个问题 —— 每个像素的范围以自己的先验为中心。
所以要的数是:**标定后,以先验为中心、多宽的相对半窗能覆盖 99% 的真值。**

三档口径都报(08-07 探针同法,便于跨素材对照):
  raw    裸米制(canonical × f_proc / 300)
  scale  逐帧稳健单尺度(中位比值)
  s+s    逐帧稳健 scale+shift(在**逆深度**上最小二乘 —— 深度先验的仿射自由度
         按惯例在视差域,直接在深度域拟合会被远处点主导)

⚠️ SfM 点不是真值,是"另一个估计"(本次重投影 1.2213 px)。这里量的是**一致性**。
⚠️ 可见性用投影近似(无观测表),遮挡点会贡献假误差 ⇒ 一律用稳健分位数,不用均值。
"""
import argparse, json, os, sys, time
import numpy as np

DA3_SRC = "/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3/src"
MODEL = ("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/"
         "ios/Runner/Models/DA3METRIC-LARGE")


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
    ap.add_argument("--cap", required=True, help="phone_cap 目录(取 photos_jpg 原图)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--res", type=int, default=504)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    meta = json.load(open(f"{args.fixture}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    CM = np.fromfile(f"{args.fixture}/cams.f32", np.float32).reshape(NF, 36)
    P = read_ply(f"{args.cap}/official_sfm_sparse.ply")
    names = meta["names"]

    cache = f"{args.out}/da3_{args.res}.npz"
    if not os.path.exists(cache):
        import torch
        sys.path.insert(0, DA3_SRC)
        from depth_anything_3.api import DepthAnything3
        import depth_anything_3.utils.logger as L
        L.logger.info = lambda *a, **k: None
        m = DepthAnything3.from_pretrained(MODEL)
        m = m.to("mps"); m.device = "mps"
        out, ts = {}, []
        for i, n in enumerate(names):
            t = time.time()
            pred = m.inference([f"{args.cap}/photos_jpg/{n}"], process_res=args.res)
            torch.mps.synchronize()
            ts.append(time.time() - t)
            out[str(i)] = pred.depth[0].astype(np.float16)
            if i % 25 == 0:
                print(f"  {i}/{NF} {out[str(i)].shape} {ts[-1]:.2f}s", flush=True)
        np.savez_compressed(cache, **out)
        print(f"DA3 推理 中位 {np.median(ts[1:]):.3f}s/帧 (res={args.res}) → {cache}")
    Z = np.load(cache)
    sh = Z["0"].shape
    print(f"DA3 输出 {sh}   fixture {W}×{H}")

    # canonical → 米:depth_m = canonical * f_proc / 300(DA3 apply_metric_scaling)
    # f_proc = 原图焦距 × (处理宽 / 原图宽);原图 4032 宽,fx 从 sidecar 取
    sc0 = json.load(open(f"{args.cap}/sidecars/{names[0].replace('.jpg','.json')}"))
    fx_orig, _, _, _ = sc0["intrinsics_fxfycxcy"]
    ow = sc0["image_w"]
    f_proc = fx_orig * (sh[1] / ow)
    print(f"f_proc = {f_proc:.2f}  (原图 fx {fx_orig:.1f} × {sh[1]}/{ow})")

    # ── 可见性:NEAR3(每点只算离它最近的 3 台相机)──
    # 🔴 必须做:全投影会把被墙/家具挡住的点也算进来,系统性抬高误差。
    #    同一把刀在 CasDiffMVS 上把 p90 从 71.6cm 拉到 8.3cm。
    #    08-07 那份 p50 1.8-2.0% 也是在可靠子集上量的 —— 不剔遮挡就是拿两把尺子比。
    Ccam = np.stack([-(CM[i, 9:18].reshape(3, 3).astype(np.float64).T
                       @ CM[i, 18:21].astype(np.float64)) for i in range(NF)])
    near3 = np.argsort(((P[:, None, :] - Ccam[None]) ** 2).sum(2), 1)[:, :3]
    vis3 = np.zeros((len(P), NF), bool)
    np.put_along_axis(vis3, near3, True, 1)

    raw, sca, ssh = [], [], []
    per_frame = []
    for i in range(NF):
        K = CM[i, 0:9].reshape(3, 3).astype(np.float64)
        R = CM[i, 9:18].reshape(3, 3).astype(np.float64)
        t = CM[i, 18:21].astype(np.float64)
        Xc = P @ R.T + t
        z = Xc[:, 2]
        ok = z > 1e-6
        uv = (Xc[ok] @ K.T)[:, :2] / z[ok, None]
        zz = z[ok]
        # fixture 像素 → DA3 输出像素(两者都是同一张原图的等比缩放)
        us = np.round(uv[:, 0] * sh[1] / W).astype(int)
        vs = np.round(uv[:, 1] * sh[0] / H).astype(int)
        m = (us >= 0) & (us < sh[1]) & (vs >= 0) & (vs < sh[0]) & \
            (zz >= CM[i, 24]) & (zz <= CM[i, 25]) & vis3[np.flatnonzero(ok), i]
        if m.sum() < 50:
            continue
        d_can = Z[str(i)][vs[m], us[m]].astype(np.float64)
        gt = zz[m]
        good = d_can > 1e-6
        d_can, gt = d_can[good], gt[good]
        d_m = d_can * f_proc / 300.0

        raw.append(np.abs(d_m - gt) / gt)
        s = np.median(gt / d_m)                       # 稳健单尺度
        sca.append(np.abs(d_m * s - gt) / gt)
        # scale+shift 在逆深度上稳健拟合(先按中位剔除极端 10%,再最小二乘)
        x, y = 1.0 / d_m, 1.0 / gt
        r0 = y - np.median(y / x) * x
        keep = np.abs(r0) < np.percentile(np.abs(r0), 90)
        A = np.stack([x[keep], np.ones(keep.sum())], 1)
        ab, *_ = np.linalg.lstsq(A, y[keep], rcond=None)
        y_hat = ab[0] * x + ab[1]
        d_ss = 1.0 / np.maximum(y_hat, 1e-6)
        e_ss = np.abs(d_ss - gt) / gt
        ssh.append(e_ss)
        per_frame.append((len(gt), float(np.median(e_ss)), float(ab[0]), float(ab[1])))

    print(f"\n参与比较 {len(per_frame)} 帧,点×帧观测 {sum(p[0] for p in per_frame):,}")
    print(f"\n{'口径':<26}{'p50':>9}{'p75':>9}{'p90':>9}{'p95':>9}{'p99':>9}")
    for nm, arr in (("raw 裸米制", raw), ("scale 逐帧单尺度", sca),
                    ("s+s 逐帧scale+shift", ssh)):
        e = np.concatenate(arr)
        print(f"{nm:<26}" + "".join(f"{100*np.percentile(e,q):8.2f}%"
                                    for q in (50, 75, 90, 95, 99)))

    e = np.concatenate(ssh)
    print(f"\n══ 能不能当逐像素范围的中心 ══")
    print(f"{'相对半窗':>10}{'覆盖率':>10}")
    for hw in (0.05, 0.10, 0.15, 0.20, 0.30, 0.50):
        print(f"{100*hw:9.0f}%{100*(e <= hw).mean():9.2f}%")
    cur = np.median(CM[:, 25] / CM[:, 24])
    print(f"\n当前整帧范围:hi/lo 中位 = {cur:.2f}×")
    for hw in (0.15, 0.20, 0.30):
        w = (1 + hw) / (1 - hw)
        print(f"  以先验为中心 ±{100*hw:.0f}% ⇒ 窗宽 {w:.2f}× "
              f"⇒ 逆深度采样密度 ×{cur/w:.1f}(覆盖 {100*(e<=hw).mean():.1f}%)")
    json.dump({"res": args.res, "f_proc": f_proc, "frames": len(per_frame),
               "p50_ss": float(np.percentile(e, 50)), "p90_ss": float(np.percentile(e, 90)),
               "p99_ss": float(np.percentile(e, 99))},
              open(f"{args.out}/da3_probe_summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
