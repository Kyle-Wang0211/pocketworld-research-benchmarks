#!/usr/bin/env python3
"""关键点尺度刀 AUC 终审(Metashape Projection Accuracy 同款判据)— cap50 host 重放。

数据:scale_knife/out_extract/session.db(生产 add_frame CPU 提取,keypoints
仿射列 = 真检测尺度,[SCALE-PERSIST 2026-08-06] 落库序即 DB 行序,零插桩)
+ scale_knife/out_model(sfm_finalize_resume_bench_exe dump 的全量 bin 模型,
不受 3° 交付过滤影响 — 过滤只在 get_points 出口)。

判据:per-point track 聚合尺度 mean/max → AUC(shell 高=坏)。
band/seed 逐字照抄 analyze_metadata_filter.py:
  shell = 1.3-2.0 m,core < 1.3(点云质心为球心),seed 0,20000 采样。
附:与视差角(max pairwise tri angle)的 Spearman(|rho|>0.9 = 换皮)。
参照:视差角 0.647 现役 / 协方差 0.635 判死 / track_len 0.326。
"""
import os
import sqlite3
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DB = sys.argv[1] if len(sys.argv) > 1 else f"{HERE}/out_extract/session.db"
MODEL = sys.argv[2] if len(sys.argv) > 2 else f"{HERE}/out_model"


def read_images_bin(path):
    """image_id -> camera centre (world). 逐字同 analyze_metadata_filter.py"""
    centres = {}
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            image_id = struct.unpack("<I", f.read(4))[0]
            qw, qx, qy, qz = struct.unpack("<dddd", f.read(32))
            tx, ty, tz = struct.unpack("<ddd", f.read(24))
            struct.unpack("<I", f.read(4))
            while f.read(1) != b"\x00":
                pass
            npts = struct.unpack("<Q", f.read(8))[0]
            f.seek(npts * 24, 1)
            q = np.array([qw, qx, qy, qz])
            q = q / np.linalg.norm(q)
            w, x, y, z = q
            R = np.array([
                [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
            ])
            centres[image_id] = -R.T @ np.array([tx, ty, tz])
    return centres


def read_points3d_bin(path):
    """xyz, err, tracks[(image_id, point2D_idx)]"""
    xyz, err, tracks = [], [], []
    with open(path, "rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        for _ in range(n):
            struct.unpack("<Q", f.read(8))
            x, y, z = struct.unpack("<ddd", f.read(24))
            f.read(3)
            e = struct.unpack("<d", f.read(8))[0]
            tlen = struct.unpack("<Q", f.read(8))[0]
            t = np.frombuffer(f.read(tlen * 8), dtype="<u4").reshape(tlen, 2)
            xyz.append((x, y, z))
            err.append(e)
            tracks.append(t.copy())
    return np.asarray(xyz), np.asarray(err), tracks


def max_pairwise_angle_deg(p, cs):
    v = cs - p
    v = v / np.linalg.norm(v, axis=1, keepdims=True)
    dot = v @ v.T
    np.fill_diagonal(dot, 1.0)
    return float(np.degrees(np.arccos(np.clip(dot.min(), -1.0, 1.0))))


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(np.float64)
    rb = np.argsort(np.argsort(b)).astype(np.float64)
    ra -= ra.mean()
    rb -= rb.mean()
    return float((ra * rb).sum() / np.sqrt((ra * ra).sum() * (rb * rb).sum()))


def main():
    # 1) per-image keypoint scales from the driver session.db (row order = DB 落库序)
    db = sqlite3.connect(DB)
    scales_of = {}
    a12max = a_asym = 0.0
    for image_id, rows, cols, data in db.execute(
            "SELECT image_id, rows, cols, data FROM keypoints"):
        a = np.frombuffer(data, dtype=np.float32).reshape(rows, cols)
        assert cols == 6, cols
        scales_of[image_id] = a[:, 2].copy()          # a11 = scale (orientation 0)
        a12max = max(a12max, float(np.abs(a[:, 3]).max()))
        a_asym = max(a_asym, float(np.abs(a[:, 2] - a[:, 5]).max()))
    all_s = np.concatenate(list(scales_of.values()))
    print(f"keypoints: images={len(scales_of)} kp={len(all_s)} "
          f"scale p10={np.percentile(all_s,10):.2f} p50={np.percentile(all_s,50):.2f} "
          f"p90={np.percentile(all_s,90):.2f} max={all_s.max():.1f}")
    print(f"affine sanity: max|a12|={a12max:.3g} max|a11-a22|={a_asym:.3g} "
          f"(both must be 0: FeatureKeypoint(x,y,scale,0))")
    print(f"unit-affine kp fraction (scale==1): {(all_s==1).mean():.4%}")

    # 2) model
    centres = read_images_bin(f"{MODEL}/images.bin")
    xyz, err, tracks = read_points3d_bin(f"{MODEL}/points3D.bin")
    n = len(xyz)
    tlen = np.array([len(t) for t in tracks])
    print(f"\nmodel points = {n}, images = {len(centres)}")
    print(f"track len: p50={np.percentile(tlen,50):.0f} "
          f"2-view={100*(tlen==2).mean():.1f}% >=3={100*(tlen>=3).mean():.1f}%")

    # 3) per-point aggregated scale + tri angle
    smean = np.empty(n)
    smax = np.empty(n)
    ang = np.empty(n)
    bad_idx = 0
    for i, t in enumerate(tracks):
        ss = []
        for iid, p2d in t:
            s_arr = scales_of.get(int(iid))
            if s_arr is None or p2d >= len(s_arr):
                bad_idx += 1
                continue
            ss.append(s_arr[p2d])
        if ss:
            smean[i] = float(np.mean(ss))
            smax[i] = float(np.max(ss))
        else:
            smean[i] = smax[i] = np.nan
        cs = np.array([centres[iid] for iid, _ in t if iid in centres])
        ang[i] = max_pairwise_angle_deg(xyz[i], cs) if len(cs) >= 2 else 0.0
    print(f"track->scale joins: bad_idx={bad_idx} "
          f"nan_points={int(np.isnan(smean).sum())}  (both must be 0)")
    print(f"max tri angle(deg): p10={np.percentile(ang,10):.2f} "
          f"p50={np.percentile(ang,50):.2f} p90={np.percentile(ang,90):.2f}")

    # 4) bands — identical to analyze_metadata_filter.py / analyze_shell.py
    centroid = xyz.mean(axis=0)
    r = np.linalg.norm(xyz - centroid, axis=1)
    shell = (r >= 1.3) & (r <= 2.0)
    core = r < 1.3
    far = r > 2.0
    print(f"radius: p50={np.percentile(r,50):.2f} p99={np.percentile(r,99):.2f} "
          f"p100={r.max():.2f}")
    print(f"bands: core={core.sum()} shell={shell.sum()} far={far.sum()}")

    def auc(metric, invert=False):
        a, b = metric[shell], metric[core]
        rng = np.random.default_rng(0)
        sa = rng.choice(a, size=min(20000, len(a)), replace=False)
        sb = rng.choice(b, size=min(20000, len(b)), replace=False)
        v = (sa[:, None] < sb[None, :]).mean() if invert \
            else (sa[:, None] > sb[None, :]).mean()
        return v

    print("\n=== AUC(shell vs core), 假说方向: 壳带点尺度大 → high=bad ===")
    print(f"mean_scale (high=bad): {auc(smean):.3f}")
    print(f"max_scale  (high=bad): {auc(smax):.3f}")
    print(f"[本模型基线] tri_angle(low=bad): {auc(ang, invert=True):.3f}  "
          f"track_len(low=bad): {auc(tlen, invert=True):.3f}  "
          f"error(high=bad): {auc(err):.3f}")

    print("\n=== Spearman vs 视差角(全点; |rho|>0.9 = 换皮)===")
    print(f"rho(mean_scale, tri_angle) = {spearman(smean, ang):+.3f}")
    print(f"rho(max_scale,  tri_angle) = {spearman(smax, ang):+.3f}")
    print(f"rho(mean_scale, track_len) = {spearman(smean, tlen.astype(float)):+.3f}")

    print("\n=== 尺度分布 core vs shell ===")
    for name, v in (("mean_scale", smean), ("max_scale", smax)):
        print(f"{name}: core p50={np.percentile(v[core],50):.2f} "
              f"p90={np.percentile(v[core],90):.2f} | "
              f"shell p50={np.percentile(v[shell],50):.2f} "
              f"p90={np.percentile(v[shell],90):.2f} | "
              f"far p50={np.percentile(v[far],50):.2f}")

    np.savez(f"{HERE}/scale_knife_metrics.npz",
             xyz=xyz, err=err, tlen=tlen, ang=ang, r=r,
             smean=smean, smax=smax)
    print(f"\nsaved -> {HERE}/scale_knife_metrics.npz")


if __name__ == "__main__":
    main()
