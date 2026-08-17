#!/usr/bin/env python3
"""对 bench_fixture97.py 存下的深度图做两件事:稀疏点指标 + 真彩 PLY。

  python3.11 eval_fixture97.py --fixture .../fixture97 --pred .../bench/C_base \
      --sparse .../official_sfm_sparse.ply --ply .../C_base.ply

⚠️ 稀疏点指标的三个已知失真(见 bench_fixture97.py 头注释),这里只报不修:
   遮挡未剔除 / 无纹理区无点 / 稀疏点自身 1.22px 重投影误差。
   ⇒ 它是**绝对锚点**,不是判决依据。判决靠肉眼看 PLY(08-17 已有先例)。
"""
import argparse, json, os
import numpy as np


def read_ply_xyz(p):
    with open(p, "rb") as f:
        hdr, n = b"", None
        while True:
            ln = f.readline()
            hdr += ln
            if ln.startswith(b"element vertex"):
                n = int(ln.split()[-1])
            if ln.strip() == b"end_header":
                break
        # x,y,z float32 + r,g,b uchar = 15 字节/点
        d = np.frombuffer(f.read(n * 15), dtype=np.dtype(
            [("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
             ("r", "u1"), ("g", "u1"), ("b", "u1")]), count=n)
    return np.stack([d["x"], d["y"], d["z"]], 1).astype(np.float64), \
           np.stack([d["r"], d["g"], d["b"]], 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--sparse", required=True)
    ap.add_argument("--ply", default="")
    ap.add_argument("--conf", type=float, default=0.5)
    args = ap.parse_args()

    FX = args.fixture
    meta = json.load(open(f"{FX}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    CM = np.fromfile(f"{FX}/cams.f32", np.float32).reshape(NF, 36)
    P, _ = read_ply_xyz(args.sparse)
    print(f"稀疏点 {len(P)}  预测帧 {NF}")

    # ── 可见性 ──
    # 出货产物里**没有** SfM 观测表(live.db 只有 keypoints/matches,无 points3D),
    # 所以"哪个点在哪帧可见"无法读出来,只能近似。两种近似都报,不二选一:
    #   ALL   每点投进所有投影落在画面内的帧 ⇒ 大量被墙/家具遮挡的点在贡献假误差,
    #         指标被系统性压低 ⇒ **悲观下界**
    #   NEAR3 每点只算离它最近的 3 台相机(实测 track_len=2.878,量级对得上)。
    #         判据只用相机位置,**不看预测深度** ⇒ 不循环论证 ⇒ **接近真值**
    Cw_cam = np.stack([-(CM[f, 9:18].reshape(3, 3).astype(np.float64).T
                         @ CM[f, 18:21].astype(np.float64)) for f in range(NF)])
    d2cam = ((P[:, None, :] - Cw_cam[None]) ** 2).sum(2)          # (npt, NF)
    near3 = np.argsort(d2cam, 1)[:, :3]
    vis3 = np.zeros((len(P), NF), bool)
    np.put_along_axis(vis3, near3, True, 1)

    tot = np.zeros(4)          # n, <1%, <3%, <5%
    tot3 = np.zeros(4)
    abs_err, abs_err3 = [], []
    for f in range(NF):
        dp = np.load(f"{args.pred}/depth/{f:04d}.npy")
        K = CM[f, 0:9].reshape(3, 3).astype(np.float64)
        R = CM[f, 9:18].reshape(3, 3).astype(np.float64)
        t = CM[f, 18:21].astype(np.float64)
        Xc = P @ R.T + t
        z = Xc[:, 2]
        ok = z > 1e-6
        uv = (Xc[ok] @ K.T)
        uv = uv[:, :2] / uv[:, 2:3]
        zz = z[ok]
        u, v = np.round(uv[:, 0]).astype(int), np.round(uv[:, 1]).astype(int)
        m = (u >= 0) & (u < W) & (v >= 0) & (v < H) & \
            (zz >= CM[f, 24]) & (zz <= CM[f, 25])
        if m.sum() == 0:
            continue
        pred = dp[v[m], u[m]]
        gt = zz[m]
        good = pred > 0
        e = np.abs(pred[good] - gt[good]) / gt[good]
        abs_err.append(np.abs(pred[good] - gt[good]))
        tot += [len(e), (e < .01).sum(), (e < .03).sum(), (e < .05).sum()]

        s = vis3[np.flatnonzero(ok)[m][good], f]                  # 该帧的 NEAR3 子集
        if s.sum():
            e3 = e[s]
            abs_err3.append(np.abs(pred[good][s] - gt[good][s]))
            tot3 += [len(e3), (e3 < .01).sum(), (e3 < .03).sum(), (e3 < .05).sum()]

    print(f"\n══ 稀疏点指标 ══")
    for label, T, AE in (("ALL  (全投影·含遮挡·悲观下界)", tot, abs_err),
                         ("NEAR3(最近3相机·接近真值)", tot3, abs_err3)):
        ae, n = np.concatenate(AE), T[0]
        print(f"{label}   观测 {int(n):>9,}")
        print(f"    <1% {100*T[1]/n:5.2f}%   <3% {100*T[2]/n:5.2f}%   <5% {100*T[3]/n:5.2f}%"
              f"   |err| 中位 {np.median(ae)*100:.2f} cm  p90 {np.percentile(ae,90)*100:.1f} cm")

    if args.ply:
        # 无融合、无几何一致性检查:每帧独立反投影后拼接。
        # 这是**看得见质量**的最朴素形式,故意不做任何清理 —— 端上融合器还没做,
        # 现在就上滤波会把"MVS 这一步到底多好"这个问题糊掉。
        from PIL import Image
        pts, cols = [], []
        for f in range(NF):
            dp = np.load(f"{args.pred}/depth/{f:04d}.npy")
            cf = np.load(f"{args.pred}/conf/{f:04d}.npy")
            if cf.shape != dp.shape:
                cf = np.array(Image.fromarray(cf).resize((dp.shape[1], dp.shape[0])))
            rgb = np.asarray(Image.open(f"{FX}/rgb/{f:08d}.jpg").resize((W, H)))
            K = CM[f, 0:9].reshape(3, 3).astype(np.float64)
            R = CM[f, 9:18].reshape(3, 3).astype(np.float64)
            t = CM[f, 18:21].astype(np.float64)
            yy, xx = np.mgrid[0:H, 0:W]
            m = (dp > 0) & (cf >= args.conf) & (dp >= CM[f, 24]) & (dp <= CM[f, 25])
            if m.sum() == 0:
                continue
            d = dp[m].astype(np.float64)
            uv1 = np.stack([xx[m], yy[m], np.ones(m.sum())], 1)
            Xc = (uv1 @ np.linalg.inv(K).T) * d[:, None]
            pts.append((Xc - t) @ R)
            cols.append(rgb[m])
        Pw = np.concatenate(pts).astype(np.float32)
        Cw = np.concatenate(cols).astype(np.uint8)
        print(f"\nPLY 点数 {len(Pw):,}  (conf≥{args.conf},无融合无清理)")
        rec = np.zeros(len(Pw), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                       ("r", "u1"), ("g", "u1"), ("b", "u1")])
        rec["x"], rec["y"], rec["z"] = Pw[:, 0], Pw[:, 1], Pw[:, 2]
        rec["r"], rec["g"], rec["b"] = Cw[:, 0], Cw[:, 1], Cw[:, 2]
        with open(args.ply, "wb") as fo:
            fo.write(f"""ply
format binary_little_endian 1.0
comment CasDiffMVS C-weights on phone_cap_20260811 fixture97 (no fusion)
element vertex {len(Pw)}
property float x
property float y
property float z
property uchar red
property uchar green
property uchar blue
end_header
""".encode())
            fo.write(rec.tobytes())
        print(f"→ {args.ply}  {os.path.getsize(args.ply)/1e6:.0f} MB")


if __name__ == "__main__":
    main()
