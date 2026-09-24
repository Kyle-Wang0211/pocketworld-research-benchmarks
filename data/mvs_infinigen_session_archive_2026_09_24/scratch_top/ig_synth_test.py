# -*- coding: utf-8 -*-
"""造一个【几何精确已知】的假 Infinigen frames 目录, 用来验 infinigen_to_blend.py 本身。

场景 = 轴对齐长方体房间, 深度用射线-平面求交解析算出 (没有渲染误差), 所以
"把深度反投影再投到另一视图" 的残差【理论上应当是 0】(只剩双线性采样和离散化)。
若转换器把 extrinsic 的方向、OpenCV 约定、K 的裁剪改写弄错, 残差会立刻爆。

camview 的写法逐字照官方 core/placement/camera.py:847-864:
    T = matrix_world @ diag(1,-1,-1,1)   # 这里直接构造 OpenCV 的 c2w
    HW = (resolution_y, resolution_x)
Depth 存 npy (blender_gt postprocess 的格式, render.py:362-363)。
"""
import os
import sys

import numpy as np
from PIL import Image

W = int(os.environ.get("IG_W", 768))
H = int(os.environ.get("IG_H", 576))
# 15mm 镜头 + adjust_camera_sensor(sensor_height 恒 18) => f_px = 15 * H/18 (aspect_probe 实测)
FX = FY = 15.0 * H / 18.0
CX, CY = W / 2.0, H / 2.0  # core/util/camera.py:57-58  u0 = W/2, v0 = H/2
K = np.array([[FX, 0, CX], [0, FY, CY], [0, 0, 1.0]])

# 房间 [0,6] x [0,5] x [0,2.7]
BOX_LO = np.array([0.0, 0.0, 0.0])
BOX_HI = np.array([6.0, 5.0, 2.7])


def look_at_c2w(eye, target, world_up=np.array([0.0, 0.0, 1.0])):
    """OpenCV 相机系 c2w: col0=right, col1=down, col2=forward"""
    f = target - eye
    f = f / np.linalg.norm(f)
    r = np.cross(f, world_up)
    r = r / np.linalg.norm(r)
    d = np.cross(f, r)                      # down = forward x right
    T = np.eye(4)
    T[:3, 0], T[:3, 1], T[:3, 2] = r, d, f
    T[:3, 3] = eye
    return T


def render_depth(T_c2w):
    """解析求交, 返回平面 Z 深度 (HxW float32)"""
    u, v = np.meshgrid(np.arange(W), np.arange(H))
    d_cam = np.stack([(u - CX) / FX, (v - CY) / FY, np.ones_like(u, dtype=float)])  # z=1
    R, t = T_c2w[:3, :3], T_c2w[:3, 3]
    d_world = np.einsum("ij,jhw->ihw", R, d_cam)
    # 对 6 个面求最小正 s: eye + s*d_world 落在 plane
    s_best = np.full((H, W), np.inf)
    for ax in range(3):
        for bound in (BOX_LO[ax], BOX_HI[ax]):
            denom = d_world[ax]
            with np.errstate(divide="ignore", invalid="ignore"):
                s = (bound - t[ax]) / denom
            p = t[:, None, None] + s[None] * d_world
            inside = np.ones((H, W), bool)
            for k in range(3):
                if k == ax:
                    continue
                inside &= (p[k] >= BOX_LO[k] - 1e-9) & (p[k] <= BOX_HI[k] + 1e-9)
            ok = np.isfinite(s) & (s > 1e-6) & inside
            s_best = np.where(ok & (s < s_best), s, s_best)
    # X_cam = d_cam * s, 而 d_cam.z == 1 => 平面深度 = s
    depth = np.where(np.isfinite(s_best), s_best, 0.0)
    return depth.astype(np.float32)


def main(out_root, n=12, seed=0):
    rng = np.random.default_rng(seed)
    center = np.array([3.0, 2.5, 1.2])
    for kind in ("Image", "Depth", "camview"):
        os.makedirs(os.path.join(out_root, kind, "camera_0"), exist_ok=True)
    for i in range(n):
        ang = 2 * np.pi * i / n
        r = 1.6 + 0.25 * rng.random()
        eye = center + np.array([r * np.cos(ang), r * np.sin(ang), 0.35 * rng.random()])
        T = look_at_c2w(eye, center + rng.normal(0, 0.05, 3))
        depth = render_depth(T)
        suffix = f"{i}_0_{1:04d}_0"
        np.save(os.path.join(out_root, "Depth", "camera_0", f"Depth_{suffix}.npy"), depth)
        np.savez(os.path.join(out_root, "camview", "camera_0", f"camview_{suffix}.npz"),
                 K=K, T=T, HW=np.array([H, W]))
        # 图像内容无关紧要, 只要非黑 (process_mvs_data.py:135 的 mean<20 过滤)
        img = (80 + 100 * rng.random((H, W, 3))).astype(np.uint8)
        Image.fromarray(img).save(
            os.path.join(out_root, "Image", "camera_0", f"Image_{suffix}.png"))
    print(f"[synth] wrote {n} views to {out_root}  (K fx={FX} cx={CX} cy={CY}, {W}x{H})")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 12)
