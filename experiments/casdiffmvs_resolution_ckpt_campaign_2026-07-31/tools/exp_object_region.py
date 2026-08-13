#!/usr/bin/env python3
"""**中心物体区域**上的各臂对照 —— 回答"物体 regime 谁更好"。

背景:这份 400+ 帧素材是**绕着一个中心物体拍的**,不是随手扫房间。所以拿整个房间
的平均指标去判"DTU 档 vs 真实场景档",会被地板/墙/窗这些大面积背景稀释掉 ——
而 DTU 档的主场恰恰就是中心物体。必须在物体那一块单独量。

"中心物体"不靠猜,用数据定义:**所有相机光轴的公共最近点**。绕拍时每台相机都对着
它,所以这些光轴(近似)交于一点。求解 min_x Σ_i dist(x, ray_i)^2 有闭式解:
    A = Σ (I - d_i d_iᵀ),  b = Σ (I - d_i d_iᵀ) o_i,  x = A⁻¹ b
然后以该点为心、R 为半径切球。

物体表面是曲面,不能用平面 RANSAC 量噪声。改用**局部曲面残差**:对每个采样点取
k 近邻拟合局部平面,记该点到局部平面的距离 —— 邻域足够小时,曲面局部近似为平面,
所以这个残差就是"这一版在物体表面上有多毛"。

用法: exp_object_region.py 标签=路径.ply [...] [--radius M] [--k K]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

RESEARCH = Path.home() / "Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python"
sys.path.insert(0, str(RESEARCH))


def lookat_point():
    """所有参考帧光轴的公共最近点(ARKit 米制系)。"""
    import pw_diffmvs_sfm_trio as T
    import geom_metrics as g
    _, refs = T.build_refs()
    mnames, K_of, w2c_of, center_of, obs, pts = T.load_model("lapa")
    ark = g.arkit_centers_and_R()
    s_al, R_al, t_al = T.robust_align(center_of, ark)

    A = np.zeros((3, 3)); b = np.zeros(3); n = 0
    for name in refs:
        w2c = w2c_of[name]
        R, t = w2c[:3, :3], w2c[:3, 3]
        o = -R.T @ t                      # 相机中心(模型系)
        d = R.T @ np.array([0.0, 0.0, 1.0])  # 光轴方向(模型系)
        d = d / np.linalg.norm(d)
        P = np.eye(3) - np.outer(d, d)
        A += P; b += P @ o; n += 1
    x_model = np.linalg.solve(A, b)
    x_ark = s_al * (R_al @ x_model) + t_al     # 转到与点云同一个 ARKit 米制系
    print(f"中心物体位置(由 {n} 条光轴解出): {np.round(x_ark,3)}", flush=True)
    return x_ark


def local_roughness(P: np.ndarray, k=30, sample=60000, seed=0):
    """局部曲面残差:每点取 k 近邻拟合平面,返回该点到局部平面的距离(mm)。"""
    if len(P) < k + 10:
        return None
    pcd = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(P))
    tree = o3d.geometry.KDTreeFlann(pcd)
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(P), min(sample, len(P)), replace=False)
    out = np.empty(len(idx))
    for j, i in enumerate(idx):
        _, nb, _ = tree.search_knn_vector_3d(pcd.points[i], k)
        Q = P[np.asarray(nb)]
        Qc = Q - Q.mean(0)
        # 最小奇异向量 = 局部平面法向
        _, _, Vt = np.linalg.svd(Qc, full_matrices=False)
        out[j] = abs((P[i] - Q.mean(0)) @ Vt[2])
    return out * 1000.0


def main() -> int:
    args, R, K = [], 0.6, 30
    it = iter(sys.argv[1:])
    for a in it:
        if a == "--radius": R = float(next(it))
        elif a == "--k": K = int(next(it))
        else: args.append(a.split("=", 1))

    c = lookat_point()
    print(f"切球半径 {R}m, 局部邻域 k={K}\n", flush=True)
    res = {"center": c.tolist(), "radius_m": R, "k": K, "arms": {}}
    print(f"{'臂':<18} {'球内点数':>10} {'占全云':>8} {'局部残差 p50':>13} {'p90':>8} {'RMS':>8}")
    for tag, path in args:
        P = np.asarray(o3d.io.read_point_cloud(path).points)
        d = np.linalg.norm(P - c, axis=1)
        Q = P[d < R]
        rgh = local_roughness(Q, k=K)
        if rgh is None:
            print(f"{tag:<18} 球内点太少({len(Q)}),跳过"); continue
        r = {"n_in_sphere": int(len(Q)), "frac_of_cloud": float(len(Q) / len(P)),
             "p50_mm": float(np.percentile(rgh, 50)), "p90_mm": float(np.percentile(rgh, 90)),
             "rms_mm": float(np.sqrt((rgh ** 2).mean()))}
        res["arms"][tag] = r
        print(f"{tag:<18} {r['n_in_sphere']:>10,} {r['frac_of_cloud']*100:>7.1f}% "
              f"{r['p50_mm']:>13.3f} {r['p90_mm']:>8.3f} {r['rms_mm']:>8.3f}")

    out = Path("/Users/kaidongwang/Documents/progecttwo/_host_fixtures/object_region.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
