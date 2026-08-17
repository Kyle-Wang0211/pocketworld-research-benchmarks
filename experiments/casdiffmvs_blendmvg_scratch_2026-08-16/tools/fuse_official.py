#!/usr/bin/env python3
"""官方融合的忠实复刻 —— **直接调用 diffmvs/filter.py 的函数,不重写判据**。

  python3.11 fuse_official.py --fixture .../fx_official --pred .../PRED --ply out.ply

🔴 08-17 记账:我先前自己写了一份 `fuse_pointcloud.py`,而仓库里本来就有官方
   `filter.py`。用户点破后核对,发现四处偏离官方:

     1. `num_view` —— 官方真实场景(ETH3D/T&T)是 **10**,我用了 5,后来 7
     2. `photo_thres` —— 官方是 **三阶段 AND [0.3, 0.5, 0.5]**,而我只存了末阶段 conf
        ⇒ 光度门形同虚设(这也是"conf≥0.5 留下 88%"的真正原因)
     3. **深度平均** —— 官方 `(Σ 一致src重投影深度 + ref) / (一致数+1)`,我完全没做
     4. 法向门 / 边缘门 —— **官方没有这两道**,那是 PocketWorld 'o' 管线自己的,
        我把两套混在了一起

   另勘误:07-31 报告说"官方真实场景 geo_pixel_thres=0.125",那是 **DTU 脚本**的值;
   ETH3D/T&T 脚本**不传**该参数 ⇒ 用 filter.py 默认 **1.0**。我原先的 1.0 是对的。

本脚本 import 官方 `check_geometric_consistency`,判据与官方**同一份代码**;
本文件只负责把 fixture 的相机/深度喂进去,并按官方 `filter_depth` 的顺序组合掩码。

官方参数(ETH3D/T&T 真实场景档,全部为 filter.py 默认或脚本显式值):
    geo_pixel_thres=1.0  geo_depth_thres=0.01  geo_mask_thres=3
    photo_thres=[0.3, 0.5, 0.5]
"""
import argparse, json, os, sys
import numpy as np

DIFFMVS = os.path.expanduser(
    "~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--ply", required=True)
    ap.add_argument("--geo-mask-thres", type=int, default=3)
    ap.add_argument("--geo-pixel-thres", type=float, default=1.0)
    ap.add_argument("--geo-depth-thres", type=float, default=0.01)
    ap.add_argument("--photo-thres", type=float, nargs=3, default=[0.3, 0.5, 0.5])
    ap.add_argument("--no-average", action="store_true", help="关掉官方的深度平均(仅对照用)")
    args = ap.parse_args()
    sys.path.insert(0, DIFFMVS)
    from filter import check_geometric_consistency        # ← 官方判据,原样调用

    FX = args.fixture
    meta = json.load(open(f"{FX}/frames.json"))
    NF, W, H = meta["count"], meta["width"], meta["height"]
    CM = np.fromfile(f"{FX}/cams.f32", np.float32).reshape(NF, 36)
    NB = np.fromfile(f"{FX}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])
    from PIL import Image

    GRAY = np.fromfile(f"{FX}/images.f16", np.float16).reshape(NF, H, W).astype(np.float32) \
        if not os.path.isdir(f"{FX}/rgb") else None
    D = [np.load(f"{args.pred}/depth/{f:04d}.npy").astype(np.float32) for f in range(NF)]
    CF = []
    for k in range(3):
        p = f"{args.pred}/conf{k}"
        if not os.path.isdir(p):
            sys.exit(f"🔴 缺 {p} —— 官方光度门要三阶段 conf,请用存三阶段的 bench 重跑")
        CF.append([np.load(f"{p}/{f:04d}.npy").astype(np.float32) for f in range(NF)])

    def cam(f):
        K = np.eye(4, dtype=np.float64)
        K[:3, :3] = CM[f, 0:9].reshape(3, 3)
        E = np.eye(4, dtype=np.float64)
        E[:3, :3] = CM[f, 9:18].reshape(3, 3)
        E[:3, 3] = CM[f, 18:21]
        return CM[f, 0:9].reshape(3, 3).astype(np.float64), E

    pts, cols = [], []
    ph_m, ge_m, fi_m = [], [], []
    for f in range(NF):
        Kr, Er = cam(f)
        ref_d = D[f]
        # ── 光度门:官方三阶段 AND ──
        photo = np.ones_like(ref_d, bool)
        for k in range(3):
            c = CF[k][f]
            if c.shape != ref_d.shape:                     # stage1 conf 可能是低分辨率
                c = np.asarray(Image.fromarray(c).resize(
                    (ref_d.shape[1], ref_d.shape[0]), Image.NEAREST))
            photo &= (c > args.photo_thres[k])

        # ── 几何门:逐源视图调官方函数 ──
        geo_sum = np.zeros_like(ref_d, np.int32)
        acc = np.zeros_like(ref_d, np.float64)
        for s in NB[f]:
            Ks, Es = cam(int(s))
            gm, d_rep, _, _ = check_geometric_consistency(
                ref_d, Kr, Er, D[int(s)], Ks, Es,
                float(CM[f, 25]), float(CM[f, 24]),
                args.geo_pixel_thres, args.geo_depth_thres)
            geo_sum += gm.astype(np.int32)
            acc += d_rep                                   # 官方:不一致处已被置 0
        # ── 官方深度平均 ──
        d_avg = ref_d.astype(np.float64) if args.no_average else \
            (acc + ref_d) / (geo_sum + 1)
        geo = geo_sum >= args.geo_mask_thres
        final = photo & geo
        ph_m.append(photo.mean()); ge_m.append(geo.mean()); fi_m.append(final.mean())
        if f % 25 == 0:
            print(f"  帧{f:3d}/{NF}  photo {photo.mean():.3f}  geo {geo.mean():.3f} "
                  f" final {final.mean():.3f}", flush=True)
        if not final.any():
            continue
        yy, xx = np.mgrid[0:H, 0:W]
        x, y, d = xx[final], yy[final], d_avg[final]
        xyz = np.linalg.inv(Kr) @ (np.vstack([x, y, np.ones_like(x)]) * d)
        Rr, tr = Er[:3, :3], Er[:3, 3]
        pts.append(((xyz.T - tr) @ Rr))
        # 老 fixture(apde_batch)没有 rgb/,只有灰度 images.f16 ⇒ 回退成灰度上色。
        # 颜色不影响任何几何判据,只影响肉眼观感,所以回退是安全的。
        pj = f"{FX}/rgb/{f:08d}.jpg"
        if os.path.exists(pj):
            rgb = np.asarray(Image.open(pj).resize((W, H)))
        else:
            g = np.clip(GRAY[f] * 255, 0, 255).astype(np.uint8)
            rgb = np.repeat(g[:, :, None], 3, 2)
        cols.append(rgb[final])

    print(f"\n══ 官方口径(geo_mask≥{args.geo_mask_thres}, geo_pixel {args.geo_pixel_thres}, "
          f"geo_depth {args.geo_depth_thres}, photo {args.photo_thres}, "
          f"深度平均 {'关' if args.no_average else '开'})══")
    print(f"  光度门存活 {100*np.mean(ph_m):.2f}%   几何门存活 {100*np.mean(ge_m):.2f}%"
          f"   最终 {100*np.mean(fi_m):.2f}%")
    P = np.concatenate(pts).astype(np.float32)
    C = np.concatenate(cols).astype(np.uint8)
    print(f"  点数 {len(P):,}")
    rec = np.zeros(len(P), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                  ("r", "u1"), ("g", "u1"), ("b", "u1")])
    rec["x"], rec["y"], rec["z"] = P[:, 0], P[:, 1], P[:, 2]
    rec["r"], rec["g"], rec["b"] = C[:, 0], C[:, 1], C[:, 2]
    with open(args.ply, "wb") as fo:
        fo.write(f"""ply
format binary_little_endian 1.0
comment CasDiffMVS official filter.py replication (ETH3D/T&T real-scene preset)
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
