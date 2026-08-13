#!/usr/bin/env python3
"""两版 TSDF 网格的表面级对照:偏差 / 粗糙度 / 覆盖。

顶点数只反映**面积**,不反映**精度** —— 896x512 和 1792x1024 在 2mm 体素下顶点数
几乎相同(9.70M vs 9.45M),但那不能说明两个面落在同一个位置、或谁更准。

没有 ground truth,所以:
  1. 对称表面偏差(A->B 与 B->A 的点到**三角面**距离,不是点到点)
     —— 只回答"差多少、差在哪",不回答谁对。
  2. 平面区粗糙度(RANSAC 拟合地板/墙面后的残差 RMS)
     —— **无 GT 也能判优劣**:真实平面上残差大的那版就是噪声大。这是核心判据。
  3. 覆盖缺口(A 上有多少点在 B 的 5mm 邻域内找不到面)
     —— 谁补了洞、谁丢了面。

用法: exp_mesh_deviation.py A.ply B.ply [SAMPLE_N]
"""
from __future__ import annotations

import json
import resource
import sys
from pathlib import Path

import numpy as np
import open3d as o3d


def peak_gb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


def load(p):
    m = o3d.io.read_triangle_mesh(p)
    print(f"  {Path(p).name}: {len(m.vertices):,} verts {len(m.triangles):,} tris",
          flush=True)
    return m


def dist_to_mesh(pts: np.ndarray, mesh) -> np.ndarray:
    """点到**三角面**的精确无符号距离(不是点到最近顶点 —— 后者会被采样密度带偏,
    密的一方天然显得更近,正是本实验要避免的伪影)。"""
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    q = o3d.core.Tensor(pts.astype(np.float32), dtype=o3d.core.Dtype.Float32)
    return scene.compute_distance(q).numpy().astype(np.float64)


def stats_mm(d: np.ndarray) -> dict:
    d = d * 1000.0
    return {"p50": float(np.percentile(d, 50)), "p90": float(np.percentile(d, 90)),
            "p99": float(np.percentile(d, 99)), "mean": float(d.mean()),
            "frac_gt2mm": float((d > 2).mean()), "frac_gt10mm": float((d > 10).mean())}


def plane_roughness(mesh, name: str, n_planes=3, thresh=0.01):
    """在网格顶点上反复 RANSAC 抽平面,报每个平面的**内点残差 RMS**。
    真实世界的地板/墙是平的,所以残差 RMS 直接就是"这一版在平面上有多噪"。
    thresh=10mm 只用来**选内点**(两版用同一个 thresh,选出的是同一批平面区域);
    RMS 在内点上算,不受 thresh 影响。"""
    pcd = o3d.geometry.PointCloud(mesh.vertices)
    out = []
    rest = pcd
    for i in range(n_planes):
        if len(rest.points) < 5000:
            break
        model, inl = rest.segment_plane(distance_threshold=thresh,
                                        ransac_n=3, num_iterations=2000)
        P = np.asarray(rest.points)[inl]
        a, b, c, d = model
        nrm = np.sqrt(a * a + b * b + c * c)
        res = np.abs(P @ np.array([a, b, c]) + d) / nrm
        out.append({"plane": i, "n_inliers": len(inl),
                    "rms_mm": float(np.sqrt((res ** 2).mean()) * 1000),
                    "p90_mm": float(np.percentile(res, 90) * 1000)})
        print(f"  [{name}] 平面{i}: {len(inl):,} 内点  RMS={out[-1]['rms_mm']:.3f}mm "
              f"p90={out[-1]['p90_mm']:.3f}mm", flush=True)
        rest = rest.select_by_index(inl, invert=True)
    return out


def main() -> int:
    pa, pb = sys.argv[1], sys.argv[2]
    N = int(sys.argv[3]) if len(sys.argv) > 3 else 800_000
    rng = np.random.default_rng(0)

    print("加载网格:", flush=True)
    A, B = load(pa), load(pb)
    VA, VB = np.asarray(A.vertices), np.asarray(B.vertices)

    ia = rng.choice(len(VA), min(N, len(VA)), replace=False)
    ib = rng.choice(len(VB), min(N, len(VB)), replace=False)

    print("A->B 表面距离…", flush=True); dab = dist_to_mesh(VA[ia], B)
    print("B->A 表面距离…", flush=True); dba = dist_to_mesh(VB[ib], A)

    res = {"A": Path(pa).name, "B": Path(pb).name, "sample_n": int(N),
           "A_to_B_mm": stats_mm(dab), "B_to_A_mm": stats_mm(dba),
           "symmetric_p50_mm": float((np.percentile(dab, 50) +
                                      np.percentile(dba, 50)) / 2 * 1000),
           # 覆盖缺口:A 上有多少采样点在 B 表面 5mm 内找不到东西
           "A_uncovered_frac_5mm": float((dab > 0.005).mean()),
           "B_uncovered_frac_5mm": float((dba > 0.005).mean())}

    print("\n平面粗糙度(核心判据,残差小=噪声小):", flush=True)
    res["planes_A"] = plane_roughness(A, "A")
    res["planes_B"] = plane_roughness(B, "B")
    res["peak_rss_GB"] = round(peak_gb(), 2)

    out = Path("/Users/kaidongwang/Documents/progecttwo/_host_fixtures/mesh_deviation.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print("\n" + json.dumps({k: v for k, v in res.items() if "planes" not in k},
                            ensure_ascii=False, indent=2))
    print(f"-> {out}  峰值 {res['peak_rss_GB']}GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
