#!/usr/bin/env python3
"""三件套收尾:对 track 延长版 work_GT16k_ext 做 track>=3 过滤真彩导出。

gauge 与 floater_forensics.py 完全同配方(相机光心 Umeyama 对到 P16KH)。
写 ply_GT16KEf3.ply,供 coverage_metric.py 对比。
"""
import numpy as np
import pycolmap as pc

EXT = "work_GT16k_ext"
REF = "work_P16kH/sparse/0"
IMGDIR = "b28_named"
OUT = "ply_GT16KEf3.ply"


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


rec = pc.Reconstruction(EXT)
n_col = rec.extract_colors_for_all_images(IMGDIR)
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
n_all = 0
for _, p3 in rec.points3D.items():
    n_all += 1
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
print(f"已写 {OUT}  {len(keep_xyz):,} 点(全 {n_all:,},删掉 {n_all - len(keep_xyz):,})"
      f"  全黑点占比 {black:.1%}", flush=True)
