#!/usr/bin/env python3
"""track 延长:把 3D 点投影回所有相机,认领附近还没归属的观测。

依据(Dense-SfM, CVPR2025):半稠密匹配产出的 track 是碎片化的、长度大多只有一对图。
它们的解法是"为 3D 点**找出更多能看到它的图像**"来延长 track。Dense-SfM 用
Gaussian Splatting 判可见性,这里用经典的重投影判据 —— 同一件事的朴素版本,
不需要训练,COLMAP 自己的 retriangulation 也是这个思路。

流程:
  1. 每台相机建一棵 KDTree,只装**还没被任何 3D 点认领**的关键点
  2. 每个 3D 点投影进每台已注册相机;落在图内、深度为正、且最近的自由关键点
     在 --px 以内 ⇒ 把它加进这个点的 track
  3. 加完跑一次 BA + 过滤,让新观测真正参与优化(不然只是账面变长)

⚠️ 这一步会**放宽**点的定义:新观测是靠几何认领的,不是靠描述子匹配来的。
   所以阈值必须紧(默认 2px,远小于建图时的 4px 重投影门),且加完必须过 BA
   和过滤 —— 认错的观测会被 BA 顶出来。质量判据仍然是重建层那几个数。
"""
import argparse
from collections import defaultdict

import numpy as np
import pycolmap as pc
from scipy.spatial import cKDTree


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rec", required=True, help="输入 sparse/0")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--px", type=float, default=2.0, help="认领半径(像素)")
    ap.add_argument("--rounds", type=int, default=2, help="认领+BA 交替轮数")
    args = ap.parse_args()

    rec = pc.Reconstruction(args.rec)
    print(f"输入:{rec.num_reg_images()} 帧 / {rec.num_points3D():,} 点 / "
          f"观测 {sum(len(p.track.elements) for p in rec.points3D.values()):,}", flush=True)

    for rnd in range(args.rounds):
        # ---- 每台相机:哪些关键点还没被认领 ----
        free_idx, trees, cams = {}, {}, {}
        for iid, im in rec.images.items():
            if not im.has_pose:
                continue
            xy, idxs = [], []
            for k, p2 in enumerate(im.points2D):
                if not p2.has_point3D():
                    xy.append(p2.xy); idxs.append(k)
            if not xy:
                continue
            free_idx[iid] = np.array(idxs)
            trees[iid] = cKDTree(np.asarray(xy))
            cfw = im.cam_from_world()
            cams[iid] = (cfw.rotation.matrix(), np.asarray(cfw.translation),
                         rec.cameras[im.camera_id])

        added, tried = 0, 0
        for pid, p3 in list(rec.points3D.items()):
            seen = {e.image_id for e in p3.track.elements}
            X = p3.xyz
            for iid, (R, t, cam) in cams.items():
                if iid in seen or iid not in trees:
                    continue
                xc = R @ X + t
                if xc[2] <= 1e-6:
                    continue
                uv = cam.img_from_cam(xc[None])[0]
                if not (0 <= uv[0] < cam.width and 0 <= uv[1] < cam.height):
                    continue
                tried += 1
                d, j = trees[iid].query(uv, k=1)
                if d > args.px:
                    continue
                k2d = int(free_idx[iid][j])
                if rec.images[iid].points2D[k2d].has_point3D():
                    continue
                try:
                    rec.add_observation(pid, pc.TrackElement(iid, k2d))
                    added += 1
                except Exception:
                    pass

        obs = sum(len(p.track.elements) for p in rec.points3D.values())
        print(f"[第{rnd+1}轮] 试探 {tried:,} 次,认领 {added:,} 个观测 → 观测总数 {obs:,}",
              flush=True)
        if added == 0:
            break

        # ---- BA:让新观测真的参与优化 ----
        # ⚠️ pycolmap 4.1 里没有 solve_bundle_adjustment / filter_all_points3D,
        #    用 create_default_bundle_adjuster + ObservationManager 的过滤
        cfg = pc.BundleAdjustmentConfig()
        for iid in cams:
            cfg.add_image(iid)
        # ⚠️ pycolmap 4.1 用 fix_gauge 定规,没有 set_constant_cam_pose。
        #    不定规 BA 会整体漂移/缩放,那样"延长有没有用"就量不准了。
        cfg.fix_gauge(pc.BundleAdjustmentGauge.THREE_POINTS)
        ba = pc.create_default_bundle_adjuster(pc.BundleAdjustmentOptions(), cfg, rec)
        ba.solve()
        obs_mgr = pc.ObservationManager(rec)
        n_f = obs_mgr.filter_all_points3D(4.0, 1.5)   # max_reproj_error, min_tri_angle
        print(f"          BA 后过滤掉 {n_f:,} 点", flush=True)

    tl = np.array([len(p.track.elements) for p in rec.points3D.values()])
    print(f"\n输出:{rec.num_reg_images()} 帧 / {rec.num_points3D():,} 点 / "
          f"观测 {int(tl.sum()):,}")
    print(f"轨迹 均值 {tl.mean():.2f} 中位 {int(np.median(tl))}  "
          f"≥3 观测 {(tl>=3).mean()*100:.1f}%  重投影 {rec.compute_mean_reprojection_error():.4f}px")
    import os
    os.makedirs(args.out, exist_ok=True)
    rec.write(args.out)
    print(f"已写出 {args.out}")


if __name__ == "__main__":
    main()
