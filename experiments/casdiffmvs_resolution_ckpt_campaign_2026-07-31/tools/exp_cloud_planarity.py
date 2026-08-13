#!/usr/bin/env python3
"""多臂稠密点云的**平面粗糙度**对照 —— 无 GT 也能判优劣的那把尺子。

今天已经反复证明**点数会骗人**:res2dtu 点数是 o 的 2.2x,但平面 RMS 一模一样。
所以"更高质量的稠密点云"必须用别的量来定义。

地板和墙在物理上是平的 → RANSAC 拟合后的**内点残差 RMS 就是这一版在平面上的
噪声水平**,不需要任何外部真值。残差小 = 面更薄 = 质量更高。

关键设计(否则会得到假结论):
 1. **所有臂用同一批平面**。各自 RANSAC 会选到不同的平面/不同的内点,残差就没法比。
    这里用第一个点云抽出平面方程,**其余臂全部复用同一组平面方程**,只在各自点云里
    按同一距离阈值取内点 —— 比的才是"同一面墙上谁更薄"。
 2. 阈值只用于**选内点**(定义"属于这面墙的点"),RMS 在内点上算,不受阈值影响。
 3. 同时报内点数 —— 残差小但点少可能只是把边缘点滤掉了,两个数要一起看。

用法: exp_cloud_planarity.py 标签=路径.ply [标签=路径.ply ...]
"""
from __future__ import annotations

import json
import resource
import sys
from pathlib import Path

import numpy as np
import open3d as o3d

INLIER_M = 0.02      # 20mm:够宽,能把两版的点都收进来;不参与 RMS 计算
N_PLANES = 4


def fit_planes(pcd, n=N_PLANES):
    """在**参考臂**上抽 n 个最大的平面,返回平面方程。其余臂复用它们。"""
    out, rest = [], pcd
    for i in range(n):
        if len(rest.points) < 20000:
            break
        model, inl = rest.segment_plane(distance_threshold=INLIER_M,
                                        ransac_n=3, num_iterations=3000)
        out.append(np.asarray(model, np.float64))
        rest = rest.select_by_index(inl, invert=True)
    return out


def residual_on_plane(P: np.ndarray, plane: np.ndarray):
    a, b, c, d = plane
    nrm = np.sqrt(a * a + b * b + c * c)
    r = np.abs(P @ np.array([a, b, c]) + d) / nrm
    m = r < INLIER_M                                  # 同一阈值选内点
    if m.sum() < 500:
        return None
    ri = r[m]
    return {"n_inliers": int(m.sum()),
            "rms_mm": float(np.sqrt((ri ** 2).mean()) * 1000),
            "p50_mm": float(np.percentile(ri, 50) * 1000),
            "p90_mm": float(np.percentile(ri, 90) * 1000)}


def main() -> int:
    args = [a.split("=", 1) for a in sys.argv[1:]]
    clouds = {}
    for tag, path in args:
        pc = o3d.io.read_point_cloud(path)
        clouds[tag] = np.asarray(pc.points)
        print(f"{tag:<16} {len(pc.points):,} 点  {Path(path).name}", flush=True)

    ref_tag = args[0][0]
    ref_pcd = o3d.geometry.PointCloud(
        o3d.utility.Vector3dVector(clouds[ref_tag]))
    planes = fit_planes(ref_pcd)
    print(f"\n在参考臂 [{ref_tag}] 上抽到 {len(planes)} 个平面,"
          f"其余臂复用同一组平面方程\n", flush=True)

    res = {"ref_arm": ref_tag, "inlier_thresh_mm": INLIER_M * 1000, "planes": []}
    print(f"{'平面':<5} {'臂':<16} {'内点数':>10} {'RMS(mm)':>9} {'p50':>7} {'p90':>7}")
    for i, pl in enumerate(planes):
        row = {"plane": i, "arms": {}}
        for tag, P in clouds.items():
            r = residual_on_plane(P, pl)
            if r is None:
                continue
            row["arms"][tag] = r
            print(f"{i:<5} {tag:<16} {r['n_inliers']:>10,} {r['rms_mm']:>9.3f} "
                  f"{r['p50_mm']:>7.3f} {r['p90_mm']:>7.3f}")
        res["planes"].append(row)
        print()

    print("=== 汇总:各臂在全部平面上的 RMS 平均(越小越好) ===")
    summ = {}
    for tag in clouds:
        vs = [p["arms"][tag]["rms_mm"] for p in res["planes"] if tag in p["arms"]]
        ns = [p["arms"][tag]["n_inliers"] for p in res["planes"] if tag in p["arms"]]
        if vs:
            summ[tag] = {"rms_mean_mm": float(np.mean(vs)),
                         "inliers_total": int(np.sum(ns)),
                         "points_total": int(len(clouds[tag]))}
            print(f"  {tag:<16} RMS均值 {np.mean(vs):6.3f}mm   "
                  f"平面内点 {np.sum(ns):>9,}   总点数 {len(clouds[tag]):>9,}")
    res["summary"] = summ
    res["peak_rss_GB"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 2)
    out = Path("/Users/kaidongwang/Documents/progecttwo/_host_fixtures/cloud_planarity.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\n-> {out}  峰值 {res['peak_rss_GB']}GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
