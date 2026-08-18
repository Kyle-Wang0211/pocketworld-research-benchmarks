#!/usr/bin/env python3
"""track 延长的向量化版 —— 与 track_extend.py 数学等价,但快两个量级。

慢版的结构是「每个 3D 点 × 每台相机」的双重 Python 循环:20 万点 × 132 相机
= 2600 万次迭代,每次一个单点 KDTree 查询 ⇒ 约 8 分钟。生产的拍完等待总共才
28.9 秒,那个数字直接出局。

这里把循环翻过来:**外层只走 132 台相机**,每台相机内部
  · 一次矩阵乘把全部 3D 点投影过去
  · 一次批量 KDTree 查询(workers=-1 多核)
Python 层的迭代次数从 2600 万降到 132。

⚠️ 一个慢版没有的正确性问题:向量化之后,**多个 3D 点可能同时认领同一个自由关键点**
   (慢版是逐个认领、认完立刻标记,天然互斥)。这里按距离升序贪心去重 —— 同一个
   关键点只归给投影最近的那个点。不做这一步会造出一对多的错观测。
"""
import argparse, os, time

import numpy as np
import pycolmap as pc
from scipy.spatial import cKDTree


def extend_round(rec, px):
    pids = np.fromiter(rec.points3D.keys(), dtype=np.int64)
    row_of = {int(p): i for i, p in enumerate(pids)}
    XYZ = np.stack([rec.points3D[int(p)].xyz for p in pids]).astype(np.float64)

    added = tried = 0
    for iid, im in rec.images.items():
        if not im.has_pose:
            continue
        p2s = im.points2D
        has3d = np.fromiter((p.has_point3D() for p in p2s), dtype=bool, count=len(p2s))
        if has3d.all():
            continue
        xy = np.stack([p.xy for p in p2s]).astype(np.float64)
        free_rows = np.flatnonzero(~has3d)
        tree = cKDTree(xy[free_rows])

        # 本相机已经看到的 3D 点 → 布尔掩码(避免重复认领)
        seen = np.zeros(len(pids), dtype=bool)
        obs_rows = [row_of.get(int(p.point3D_id)) for p in p2s if p.has_point3D()]
        obs_rows = [r for r in obs_rows if r is not None]
        if obs_rows:
            seen[np.asarray(obs_rows)] = True

        cfw = im.cam_from_world()
        R = cfw.rotation.matrix(); t = np.asarray(cfw.translation)
        cam = rec.cameras[im.camera_id]

        xc = XYZ @ R.T + t                       # 一次矩阵乘,全部点
        ok = (xc[:, 2] > 1e-6) & ~seen
        cand = np.flatnonzero(ok)
        if cand.size == 0:
            continue
        uv = cam.img_from_cam(xc[cand])
        inb = ((uv[:, 0] >= 0) & (uv[:, 0] < cam.width)
               & (uv[:, 1] >= 0) & (uv[:, 1] < cam.height))
        cand, uv = cand[inb], uv[inb]
        if cand.size == 0:
            continue
        tried += cand.size

        d, j = tree.query(uv, k=1, workers=-1)   # 批量查询,多核
        hit = d <= px
        cand, j, d = cand[hit], j[hit], d[hit]
        if cand.size == 0:
            continue

        # ⚠️ 去重:同一个自由关键点只归给投影最近的那个 3D 点
        order = np.argsort(d, kind="stable")
        cand, j = cand[order], j[order]
        _, first = np.unique(j, return_index=True)
        cand, j = cand[first], j[first]

        for r, jj in zip(cand, j):
            k2d = int(free_rows[jj])
            try:
                rec.add_observation(int(pids[r]), pc.TrackElement(iid, k2d))
                added += 1
            except Exception:
                pass
    return added, tried


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--px", type=float, default=2.0)
    ap.add_argument("--rounds", type=int, default=2)
    args = ap.parse_args()

    rec = pc.Reconstruction(args.rec)
    n0 = sum(len(p.track.elements) for p in rec.points3D.values())
    print(f"输入:{rec.num_reg_images()} 帧 / {rec.num_points3D():,} 点 / 观测 {n0:,}", flush=True)

    t_all = time.perf_counter()
    for rnd in range(args.rounds):
        t0 = time.perf_counter()
        added, tried = extend_round(rec, args.px)
        t_claim = time.perf_counter() - t0
        obs = sum(len(p.track.elements) for p in rec.points3D.values())
        print(f"[第{rnd+1}轮] 试探 {tried:,} 认领 {added:,} → 观测 {obs:,}  "
              f"认领耗时 {t_claim:.1f}s", flush=True)
        if added == 0:
            break
        t0 = time.perf_counter()
        cfg = pc.BundleAdjustmentConfig()
        for iid, im in rec.images.items():
            if im.has_pose:
                cfg.add_image(iid)
        cfg.fix_gauge(pc.BundleAdjustmentGauge.THREE_POINTS)
        pc.create_default_bundle_adjuster(pc.BundleAdjustmentOptions(), cfg, rec).solve()
        n_f = pc.ObservationManager(rec).filter_all_points3D(4.0, 1.5)
        print(f"          BA+过滤 {time.perf_counter()-t0:.1f}s,滤掉 {n_f:,} 点", flush=True)

    tl = np.array([len(p.track.elements) for p in rec.points3D.values()])
    print(f"\n总耗时 {time.perf_counter()-t_all:.1f}s")
    print(f"输出:{rec.num_reg_images()} 帧 / {rec.num_points3D():,} 点 / 观测 {int(tl.sum()):,}")
    print(f"轨迹 均值 {tl.mean():.2f} 中位 {int(np.median(tl))}  "
          f"≥3 观测 {(tl>=3).mean()*100:.1f}%  重投影 {rec.compute_mean_reprojection_error():.4f}px")
    os.makedirs(args.out, exist_ok=True)
    rec.write(args.out)
    print(f"已写出 {args.out}")


if __name__ == "__main__":
    main()
