#!/usr/bin/env python3
"""臂 L:LoFTR-indoor(detector-free)——按 08-17 这套口径重量一遍。

为什么重量:07-13 判 detector-free "不是净赢"的三条质量论据(地板 band_std /
ptp / 选区可分性)量的都是**鬼层(表面多层壳=双地板 2-3.5cm 第二层)**,
而鬼层后来被 AR 那条线解决了 ⇒ 那三条证据全部过期,结论必须重做。
没过期的只有两条:ELoFTR 只有室外权重(所以这里用 LoFTR-indoor 的 ScanNet 权重),
以及 detector-free 无跨 pair 关键点身份(下面这段量化就是在补这个)。

🔑 核心难点:detector-free **每对各自出亚像素对应,跨 pair 没有共享 keypoint 身份**
   —— 不能像 LightGlue 那样只换 matcher 槽位。要进 COLMAP 必须先造"虚拟关键点":
   把所有对的端点按网格四舍五入 → 同格并成一个规范 id → track 才闭合得起来。
   这是 hloc/DFSfM 的标准做法(cell_size 起点 8px),也是旧账里记的
   "track 闭合根治 detector-free 头号病:每 pair 坐标不一致"。

⚠️ 分辨率:LoFTR-indoor 在 ScanNet 640×480 上训练。我们的原图 4032×3024 正好也是
   4:3,所以 640×480 不引入畸变(旧账里 ELoFTR 那次 16:9 畸变的坑在这里不存在)。
"""
import argparse, json, shutil, sqlite3, time
from collections import defaultdict
from pathlib import Path

import numpy as np
import torch

import devutil

MAX_IMAGE_ID = 2147483647


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--frame-map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--weights", default="indoor", choices=["indoor", "outdoor"])
    ap.add_argument("--long-side", type=int, default=640,
                    help="LoFTR 输入长边(短边按 4:3 推)。640×480 = ScanNet 训练分辨率")
    ap.add_argument("--conf-thr", type=float, default=0.2,
                    help="mconf 阈值。0.2 是 LoFTR/ELoFTR/hloc/DFSfM 的全球统一默认")
    ap.add_argument("--merge", default="grid", choices=["grid", "kdtree"],
                    help="grid=硬网格四舍五入(有边界病:相距 1px 只要跨格线就分成两个 id);"
                         "kdtree=半径贪心合并(hloc/DFSfM 的正规做法,无边界病)")
    ap.add_argument("--radius", type=float, default=8.0,
                    help="--merge kdtree 的合并半径(原图像素)。同一 3D 点在不同对里的观测"
                         "应落在 1-2 个 LoFTR 像素内 = 原图 6-12px")
    ap.add_argument("--cell", type=float, default=8.0,
                    help="虚拟关键点的网格边长(原图像素)。太大→坐标失真,太小→track 连不起来")
    ap.add_argument("--pairs", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    from kornia.feature import LoFTR
    import kornia
    dev = torch.device(args.device)
    devutil.strict_fp32()
    matcher = LoFTR(pretrained=args.weights).eval().to(dev)

    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    names = {i: n for i, n in db.execute("select image_id,name from images")}
    pairs = [p for (p,) in db.execute("select pair_id from matches order by pair_id")]
    base = {p: r for p, r in db.execute("select pair_id,rows from matches")}
    db.close()
    if args.pairs:
        step = max(1, len(pairs) // args.pairs)
        pairs = pairs[::step][:args.pairs]

    fmap = json.load(open(args.frame_map))
    imgdir = Path(args.images)

    # ---- 灰度图常驻显存(132 帧 × 640×480 × 4B = 162MB,放得下)----
    from PIL import Image
    gray, scale = {}, {}
    for iid in names:
        im = Image.open(imgdir / fmap[str(iid)]).convert("L")
        W0, H0 = im.size
        s = args.long_side / max(W0, H0)
        w, h = int(round(W0 * s / 8)) * 8, int(round(H0 * s / 8)) * 8   # LoFTR 粗层 1/8
        g = torch.from_numpy(np.asarray(im.resize((w, h), Image.BILINEAR),
                                        dtype=np.float32) / 255.0)
        gray[iid] = g[None, None].to(dev)
        scale[iid] = (W0 / w, H0 / h)      # 回原图坐标的比例
    print(f"载入 {len(gray)} 帧灰度图 @ {w}×{h}", flush=True)

    # ---- 逐对匹配,先把对应攒起来(还没有关键点身份)----
    raw, t_m = [], 0.0
    for i, pid in enumerate(pairs):
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        if i1 not in gray or i2 not in gray:
            continue
        t0 = time.perf_counter()
        with torch.no_grad():
            o = matcher({"image0": gray[i1], "image1": gray[i2]})
        devutil.sync(dev)
        t_m += time.perf_counter() - t0
        c = o["confidence"].cpu().numpy()
        k = c >= args.conf_thr
        p0 = o["keypoints0"].cpu().numpy()[k] * np.array(scale[i1])
        p1 = o["keypoints1"].cpu().numpy()[k] * np.array(scale[i2])
        raw.append((pid, i1, i2, p0.astype(np.float32), p1.astype(np.float32)))
        if i < 3 or (i + 1) % 200 == 0:
            print(f"  [{i+1}/{len(pairs)}] 对应 {k.sum():5d} base={base.get(pid,0):5d} "
                  f"{(time.perf_counter()-t0)*1000:6.1f}ms", flush=True)

    n_corr = sum(len(r[3]) for r in raw)
    print(f"\n匹配完成:{len(raw)} 对,平均 {n_corr/len(raw):.0f} 对应/对,"
          f"{t_m/len(raw)*1000:.1f} ms/对", flush=True)

    # ---- 网格量化:把散落的对应端点并成规范关键点 ----
    #      同一格内的多个端点取坐标均值(比取首个更稳,亚像素信息不浪费)
    def build_grid(pts_per_img):
        kp, lut = {}, {}
        for iid, pts in pts_per_img.items():
            cells = np.floor(pts / args.cell).astype(np.int64)
            ids, arr, acc = {}, [], defaultdict(list)
            for c, xy in zip(map(tuple, cells), pts):
                acc[c].append(xy)
            for c, xs in acc.items():
                ids[c] = len(arr); arr.append(np.mean(xs, axis=0))
            kp[iid] = np.asarray(arr, dtype=np.float32)
            lut[iid] = ("grid", ids)
        return kp, lut

    def build_kdtree(pts_per_img):
        """半径贪心合并:每次取一个未分配点,把半径内所有未分配点并成一个规范关键点。

        比硬网格好在没有边界病 —— 相距 1px 的两个观测一定并到一起,而网格法
        只要它们跨了格线就会分成两个 id,track 当场断掉。
        """
        from scipy.spatial import cKDTree
        kp, lut = {}, {}
        for iid, pts in pts_per_img.items():
            tree = cKDTree(pts)
            assign = np.full(len(pts), -1, dtype=np.int64)
            centers = []
            for i in range(len(pts)):
                if assign[i] >= 0:
                    continue
                nb = np.array(tree.query_ball_point(pts[i], args.radius), dtype=np.int64)
                nb = nb[assign[nb] < 0]
                assign[nb] = len(centers)
                centers.append(pts[nb].mean(axis=0))
            kp[iid] = np.asarray(centers, dtype=np.float32)
            lut[iid] = ("kdtree", cKDTree(kp[iid]))
        return kp, lut

    # 先把每帧的所有端点摊平(含来自哪一对、第几个,便于回填)
    pts_per_img = defaultdict(list)
    for _pid, i1, i2, p0, p1 in raw:
        pts_per_img[i1].append(p0); pts_per_img[i2].append(p1)
    pts_per_img = {k: np.concatenate(v, 0) for k, v in pts_per_img.items()}
    n_endpoint = sum(len(v) for v in pts_per_img.values())

    t0 = time.perf_counter()
    kpts, lut = (build_kdtree if args.merge == "kdtree" else build_grid)(pts_per_img)
    n_kp = sum(len(v) for v in kpts.values())
    tag = f"半径 {args.radius:.0f}px" if args.merge == "kdtree" else f"cell {args.cell:.0f}px"
    print(f"{args.merge} 合并({tag}):平均 {n_kp/len(kpts):.0f} 虚拟关键点/帧,"
          f"压缩 {n_endpoint/n_kp:.2f}× 端点→关键点,耗时 {time.perf_counter()-t0:.1f}s", flush=True)

    # ---- 用规范 id 重写每对的匹配 ----
    def to_ids(iid, pts):
        kind, obj = lut[iid]
        if kind == "grid":
            return np.array([obj[tuple(c)] for c in
                             np.floor(pts / args.cell).astype(np.int64)], dtype=np.int64)
        return obj.query(pts, k=1)[1]          # 最近的规范关键点

    out_rows, n_lg, n_base = [], 0, 0
    for pid, i1, i2, p0, p1 in raw:
        m = np.stack([to_ids(i1, p0), to_ids(i2, p1)], 1).astype(np.uint32)
        m = np.unique(m, axis=0)               # 合并后可能重复,COLMAP 不接受
        out_rows.append((pid, m))
        n_lg += len(m); n_base += base.get(pid, 0)

    k = len(out_rows)
    print(f"\n=== {k} 对 ===")
    print(f"LoFTR-{args.weights} 平均 {n_lg/k:8.1f} 匹配/对(量化去重后)")
    print(f"基线(DSP-SIFT 暴力+0.8) 平均 {n_base/k:8.1f}")
    print(f"比值 {n_lg/max(n_base,1):.3f}×")

    shutil.copy(args.db, args.out)
    for suf in ("-wal", "-shm"):
        Path(args.out + suf).unlink(missing_ok=True)
    o = sqlite3.connect(args.out)
    o.execute("delete from keypoints"); o.execute("delete from descriptors")
    o.execute("delete from matches");   o.execute("delete from two_view_geometries")
    for iid, kp in kpts.items():
        o.execute("insert into keypoints(image_id,rows,cols,data) values(?,?,?,?)",
                  (iid, kp.shape[0], 2, kp.tobytes()))
    for pid, m in out_rows:
        o.execute("insert into matches(pair_id,rows,cols,data) values(?,?,?,?)",
                  (pid, m.shape[0], 2, m.tobytes()))
    o.commit(); o.close()
    print(f"已写出 {args.out}")


if __name__ == "__main__":
    main()
