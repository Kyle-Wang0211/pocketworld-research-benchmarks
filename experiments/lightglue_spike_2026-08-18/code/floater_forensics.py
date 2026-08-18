#!/usr/bin/env python3
"""浮点法医:验证"浮点≡2-view 点"假说 + 产出 track>=3 过滤版真彩 PLY。

跑法(盒子上,venv_colmap 的 python,纯 CPU):
  cd /workspace/lgspike && venv_colmap/bin/python -u floater_forensics.py

四件事:
  1. work_GT16k track 长度分布(2/3/>=4)
  2. 孤立度 x track 交叉表:每点到云内第 k=10 近邻距离,top10% 最远 = 孤立点,
     对比孤立点 vs 其余点里 track=2 的占比(cKDTree 全量,不抽样)
  3. 过滤版导出:跳过 track<3 的点,真彩,gauge 用相机光心 Umeyama 对到 P16KH
     (与 export_ply.py 同一配方),写 ply_GT16Kf3.ply
  4. work_GT16k_ext(track 延长后)同样的 track 分布 —— 看 2-view 尾巴缩了多少
"""
import numpy as np
import pycolmap as pc
from pathlib import Path
from scipy.spatial import cKDTree

WORK = "work_GT16k/sparse/0"
EXT = "work_GT16k_ext"            # 裸模型目录
REF = "work_P16kH/sparse/0"
IMGDIR = "b28_named"
OUT = "ply_GT16Kf3.ply"


def track_stats(rec, name):
    tl = np.array([len(p3.track.elements) for _, p3 in rec.points3D.items()])
    n = len(tl)
    print(f"\n=== {name}: {n:,} 点 ===")
    print(f"track=2   : {(tl == 2).sum():>8,}  ({(tl == 2).mean():.1%})")
    print(f"track=3   : {(tl == 3).sum():>8,}  ({(tl == 3).mean():.1%})")
    print(f"track=4   : {(tl == 4).sum():>8,}  ({(tl == 4).mean():.1%})")
    print(f"track>=4  : {(tl >= 4).sum():>8,}  ({(tl >= 4).mean():.1%})")
    print(f"track>=3  : {(tl >= 3).sum():>8,}  ({(tl >= 3).mean():.1%})")
    print(f"均值 {tl.mean():.2f}  中位 {np.median(tl):.0f}", flush=True)
    return tl


def umeyama(src, dst):
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    C = b.T @ a / len(src)
    U, D, Vt = np.linalg.svd(C)
    S_ = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S_[2, 2] = -1
    R = U @ S_ @ Vt
    s = (D * np.diag(S_)).sum() / (a ** 2).sum() * len(src)
    t = mu_d - s * R @ mu_s
    return s, R, t


def main():
    rec = pc.Reconstruction(WORK)
    tl = track_stats(rec, "GT16K(极线门臂,过滤前)")

    # ---- 2) 孤立度 x track 交叉表(全量 kNN, k=10) ----
    xyz = np.array([p3.xyz for _, p3 in rec.points3D.items()])
    tree = cKDTree(xyz)
    d, _ = tree.query(xyz, k=11, workers=-1)     # 第 0 列是自己
    d10 = d[:, 10]
    print(f"\n=== 孤立度(到第10近邻距离) x track 交叉表 ===")
    print(f"d10 中位 {np.median(d10):.4f}  p90 {np.percentile(d10, 90):.4f}")
    for topf in (0.05, 0.10, 0.20):
        thr = np.quantile(d10, 1 - topf)
        iso = d10 >= thr
        f_iso = (tl[iso] == 2).mean()
        f_rest = (tl[~iso] == 2).mean()
        print(f"top{topf:.0%} 孤立({iso.sum():,}点): track=2 占 {f_iso:.1%}"
              f" | 非孤立: track=2 占 {f_rest:.1%}  比值 {f_iso / f_rest:.2f}x")
    # 反向:track=2 的点里孤立(top10%)占比 vs track>=3 里
    thr10 = np.quantile(d10, 0.90)
    iso10 = d10 >= thr10
    print(f"反向: track=2 的点里 top10%孤立占 {iso10[tl == 2].mean():.1%}"
          f" | track>=3 的点里占 {iso10[tl >= 3].mean():.1%}")
    print(f"top10% 孤立点里被 track<3 过滤删掉的比例: {(tl[iso10] < 3).mean():.1%}", flush=True)
    # 孤立度均值对比
    print(f"track=2 点 d10 中位 {np.median(d10[tl == 2]):.4f}"
          f" | track>=3 点 d10 中位 {np.median(d10[tl >= 3]):.4f}", flush=True)

    # ---- 3) 过滤版真彩导出, gauge 对到 P16KH ----
    n_col = rec.extract_colors_for_all_images(IMGDIR)
    print(f"\n取色 {'成功' if n_col else '⚠️ 返回 False'}", flush=True)
    ref = pc.Reconstruction(REF)
    ref_c = {i: im.projection_center() for i, im in ref.images.items() if im.has_pose}
    cur_c = {i: im.projection_center() for i, im in rec.images.items() if im.has_pose}
    shared = sorted(set(cur_c) & set(ref_c))
    src = np.array([cur_c[i] for i in shared])
    dst = np.array([ref_c[i] for i in shared])
    s, R, t = umeyama(src, dst)
    resid = np.linalg.norm((s * (R @ src.T).T + t) - dst, axis=1)
    print(f"gauge 对齐用 {len(shared)} 台相机  尺度 {s:.4f}"
          f"  残差 中位 {np.median(resid):.4f} p90 {np.percentile(resid, 90):.4f}", flush=True)

    keep_xyz, keep_rgb = [], []
    for _, p3 in rec.points3D.items():
        if len(p3.track.elements) >= 3:
            keep_xyz.append(p3.xyz)
            keep_rgb.append(p3.color)
    keep_xyz = s * (R @ np.array(keep_xyz).T).T + t
    keep_rgb = np.array(keep_rgb, dtype=np.uint8)
    with open(OUT, "wb") as f:
        f.write(f"ply\nformat binary_little_endian 1.0\nelement vertex {len(keep_xyz)}\n"
                "property float x\nproperty float y\nproperty float z\n"
                "property uchar red\nproperty uchar green\nproperty uchar blue\n"
                "end_header\n".encode())
        r_ = np.zeros(len(keep_xyz), dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                            ("r", "u1"), ("g", "u1"), ("b", "u1")])
        r_["x"], r_["y"], r_["z"] = keep_xyz[:, 0], keep_xyz[:, 1], keep_xyz[:, 2]
        r_["r"], r_["g"], r_["b"] = keep_rgb[:, 0], keep_rgb[:, 1], keep_rgb[:, 2]
        f.write(r_.tobytes())
    black = (keep_rgb.sum(1) == 0).mean()
    print(f"已写 {OUT}  {len(keep_xyz):,} 点(删掉 {len(xyz) - len(keep_xyz):,})"
          f"  全黑点占比 {black:.1%}", flush=True)

    # ---- 4) track 延长版分布 ----
    rec_e = pc.Reconstruction(EXT)
    tl_e = track_stats(rec_e, "GT16K_ext(track 延长后)")
    print(f"\n2-view 尾巴: 过滤前 {(tl == 2).mean():.1%} -> 延长后 {(tl_e == 2).mean():.1%}")


if __name__ == "__main__":
    main()
