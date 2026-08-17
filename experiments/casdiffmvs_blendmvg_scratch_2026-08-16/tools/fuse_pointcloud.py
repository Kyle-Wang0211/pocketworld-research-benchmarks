#!/usr/bin/env python3
"""几何一致性融合 —— 把逐帧深度图变成一份可看的点云。

  python3.11 fuse_pointcloud.py --fixture ... --pred ... --ply out.ply --min-views 2

🔴 为什么必须有这一步(08-17 事故记账):
   我先前出的 PLY 只用 `conf>=0.5` 过滤,理由是"怕滤波糊掉 MVS 本身的质量"。
   结果 87.9% 的像素全留下,侧面看是一堆扇形薄片。诊断后:
     · 深度范围贴边只有 0.05% ⇒ 不是范围截断
     · **26.47% 的像素零个源视图认同** ⇒ 薄片全是这些
     · 而零认同像素的 conf 中位数是 **0.606,比 0.5 还高** ⇒ 那道闸门形同虚设
   **单靠 conf 阈值滤不掉错误深度,必须做几何一致性。** 这是 COLMAP `stereo_fusion`
   与整个 MVSNet 家族的标准做法,不是我发明的清理。

⚖️ 这与"交付绝对无损/禁降采样"不冲突:删掉的是**几何上被证伪的点**,
   不是把正确的点抽稀。正确表面的点一个不少。

判据(逐源视图):
   参考帧像素 p 深度 d → 投到源视图 → 取源视图在那里估的深度 → 反投世界 → 投回参考帧
   要求 重投影误差 < reproj_px 且 相对深度差 < depth_tol
"""
import argparse, json, os
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--ply", required=True)
    ap.add_argument("--min-views", type=int, default=2,
                    help="要求几个源视图几何一致(MVSNet 家族常用 2–3)")
    ap.add_argument("--reproj-px", type=float, default=1.0)
    ap.add_argument("--depth-tol", type=float, default=0.01)
    ap.add_argument("--conf", type=float, default=0.0,
                    help="额外的 conf 闸门。默认 0 = 不用 —— 几何一致性已经把活干了,"
                         "而且实测 conf 单独用是无效闸门")
    ap.add_argument("--normal-thres", type=float, default=0.0,
                    help="法向门:|cos(法向,视线)| 下限。生产签决口径 0.5,0=关")
    ap.add_argument("--edge-thres", type=float, default=0.0,
                    help="边缘门:相对深度梯度上限。生产签决口径 0.03,0=关")
    ap.add_argument("--average", action="store_true",
                    help="用一致视图的深度做平均(标准融合做法,降噪)")
    args = ap.parse_args()

    FX = args.fixture
    meta = json.load(open(f"{FX}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    CM = np.fromfile(f"{FX}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{FX}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])
    D = [np.load(f"{args.pred}/depth/{f:04d}.npy").astype(np.float64) for f in range(NF)]
    C = [np.load(f"{args.pred}/conf/{f:04d}.npy") for f in range(NF)]
    from PIL import Image

    def cam(f):
        return (CM[f, 0:9].reshape(3, 3).astype(np.float64),
                CM[f, 9:18].reshape(3, 3).astype(np.float64),
                CM[f, 18:21].astype(np.float64))

    yy, xx = np.mgrid[0:H, 0:W]
    uv1 = np.stack([xx, yy, np.ones((H, W))], -1).reshape(-1, 3)
    pts, cols = [], []
    kept = total = 0
    for f in range(NF):
        Kr, Rr, tr = cam(f)
        dr = D[f].reshape(-1)
        Xc = (uv1 @ np.linalg.inv(Kr).T) * dr[:, None]
        Xw = (Xc - tr) @ Rr
        agree = np.zeros(H * W, np.int32)
        dsum = dr.copy()
        for s in NB[f]:
            Ks, Rs, ts = cam(int(s))
            Xs = Xw @ Rs.T + ts
            zs = Xs[:, 2]
            ok = zs > 1e-6
            us = np.full(H * W, -1); vs = np.full(H * W, -1)
            proj = np.zeros((H * W, 2))
            proj[ok] = (Xs[ok] @ Ks.T)[:, :2] / zs[ok, None]
            us[ok] = np.round(proj[ok, 0]); vs[ok] = np.round(proj[ok, 1])
            inb = ok & (us >= 0) & (us < W) & (vs >= 0) & (vs < H)
            idx = np.flatnonzero(inb)
            if idx.size == 0:
                continue
            ds = D[int(s)][vs[idx].astype(int), us[idx].astype(int)]
            uv1s = np.stack([us[idx], vs[idx], np.ones(idx.size)], -1)
            Xcs = (uv1s @ np.linalg.inv(Ks).T) * ds[:, None]
            Xrb = ((Xcs - ts) @ Rs) @ Rr.T + tr
            zrb = Xrb[:, 2]
            good = zrb > 1e-6
            uvb = np.full((idx.size, 2), 1e9)
            uvb[good] = (Xrb[good] @ Kr.T)[:, :2] / zrb[good, None]
            reproj = np.hypot(uvb[:, 0] - xx.ravel()[idx], uvb[:, 1] - yy.ravel()[idx])
            ddiff = np.abs(zrb - dr[idx]) / np.maximum(dr[idx], 1e-6)
            hit = good & (reproj < args.reproj_px) & (ddiff < args.depth_tol)
            agree[idx[hit]] += 1
            if args.average:
                dsum[idx[hit]] += zrb[hit]

        m = agree >= args.min_views
        if args.conf > 0:
            m &= C[f].reshape(-1) >= args.conf

        # ── 法向门(生产口径 0.5)──
        # 深度梯度求表面法向,与视线夹角太掠射的像素判掉:掠射面上一个像素跨越
        # 很大的深度差,这类点位置误差被几何门放过但实际很不准。
        if args.normal_thres > 0:
            dz = D[f]
            gy, gx = np.gradient(dz)
            fx_, fy_ = Kr[0, 0], Kr[1, 1]
            # 法向 ∝ (-fx*∂d/∂x, -fy*∂d/∂y, d + x*∂d/∂x + y*∂d/∂y) 的归一化
            nx = -fx_ * gx
            ny = -fy_ * gy
            nz = dz + (xx - Kr[0, 2]) * gx + (yy - Kr[1, 2]) * gy
            nn = np.sqrt(nx**2 + ny**2 + nz**2) + 1e-12
            cosang = np.abs(nz / nn)          # 视线为 +Z ⇒ 与法向夹角余弦
            m &= (cosang.reshape(-1) >= args.normal_thres)

        # ── 边缘门(生产口径 0.03)──
        # 深度不连续处的像素:插值出来的"边坡"点,既不属于前景也不属于背景。
        if args.edge_thres > 0:
            dz = D[f]
            gy, gx = np.gradient(dz)
            rel = np.hypot(gx, gy) / np.maximum(dz, 1e-6)
            m &= (rel.reshape(-1) <= args.edge_thres)
        total += H * W
        kept += int(m.sum())
        if not m.any():
            continue
        dfin = (dsum[m] / (agree[m] + 1)) if args.average else dr[m]
        Xc2 = (uv1[m] @ np.linalg.inv(Kr).T) * dfin[:, None]
        pts.append((Xc2 - tr) @ Rr)
        rgb = np.asarray(Image.open(f"{FX}/rgb/{f:08d}.jpg").resize((W, H)))
        cols.append(rgb.reshape(-1, 3)[m])
        if f % 25 == 0:
            print(f"  帧{f:3d}/{NF}  留 {100*m.mean():5.1f}%", flush=True)

    P = np.concatenate(pts).astype(np.float32)
    Cc = np.concatenate(cols).astype(np.uint8)
    print(f"\n几何一致性 ≥{args.min_views} 视图 ⇒ 留下 {kept:,}/{total:,} ({100*kept/total:.2f}%)")
    print(f"点数 {len(P):,}   深度平均 {'开' if args.average else '关'}")
    rec = np.zeros(len(P), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                  ("r", "u1"), ("g", "u1"), ("b", "u1")])
    rec["x"], rec["y"], rec["z"] = P[:, 0], P[:, 1], P[:, 2]
    rec["r"], rec["g"], rec["b"] = Cc[:, 0], Cc[:, 1], Cc[:, 2]
    with open(args.ply, "wb") as fo:
        fo.write(f"""ply
format binary_little_endian 1.0
comment CasDiffMVS geometric-consistency fusion min_views={args.min_views}
element vertex {len(P)}
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
