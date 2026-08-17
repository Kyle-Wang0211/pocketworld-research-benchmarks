#!/usr/bin/env python3
"""覆盖 vs 形状:给稀疏云的两把尺子。

为什么要先立尺子:用户的判断是「B2 形状更准,RaCo 覆盖更大」,而我到目前为止报的
全是点数/观测/轨迹长度 —— **一个字都没量覆盖**。按旧账(换掉错尺子那次),
在没有正确尺子之前调参数,量到的会是别的东西。

覆盖(coverage):占据体素数。云已用相机光心统一 gauge,尺度可比,所以固定物理体素边长
数占据格子就是「铺到了多少地方」。同时给几个边长,避免单一尺度的结论。

形状(shape):
  - 轨迹长度 —— 点被几台相机看到,薄点=噪声点
  - 局部离散度 —— 每点到其 k 近邻的中位距离的分布。同样覆盖下这个值越小,面越实
  - 每占据体素的点数 —— 密度;覆盖大但每格只有 1-2 点 = 摊薄不是铺开

⚠️ 覆盖不能只看包围盒:一颗飞点就能把包围盒撑大。体素占据对离群点不敏感,
   而且和「用户看到铺满没有」这个体感直接对应。
"""
import argparse, json
from pathlib import Path

import numpy as np


def read_ply(p):
    with open(p, "rb") as f:
        hdr = b""
        while not hdr.endswith(b"end_header\n"):
            hdr += f.read(1)
        n = int([l for l in hdr.decode().splitlines()
                 if l.startswith("element vertex")][0].split()[-1])
        rec = np.frombuffer(f.read(), count=n,
                            dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                                   ("r", "u1"), ("g", "u1"), ("b", "u1")])
    return np.stack([rec["x"], rec["y"], rec["z"]], 1).astype(np.float64)


def occupied(xyz, size):
    return len(np.unique(np.floor(xyz / size).astype(np.int64), axis=0))


def knn_spread(xyz, k=8, sample=20000, seed=0):
    """每点到第 k 近邻的距离(抽样)。用分块暴力算,免依赖。"""
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(xyz), min(sample, len(xyz)), replace=False)
    q = xyz[idx]
    out = np.empty(len(q))
    B = 512
    for i in range(0, len(q), B):
        d = np.linalg.norm(q[i:i + B, None, :] - xyz[None, :, :], axis=2)
        d.sort(axis=1)
        out[i:i + B] = d[:, k]        # 第 0 列是自己
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plys", required=True, help="标签=文件.ply,逗号分隔")
    ap.add_argument("--works", default="", help="标签=工作目录,逗号分隔(读 metrics.json)")
    ap.add_argument("--voxels", default="0.02,0.05,0.10,0.20")
    ap.add_argument("--knn-sample", type=int, default=8000)
    args = ap.parse_args()

    sizes = [float(x) for x in args.voxels.split(",")]
    works = dict(x.split("=", 1) for x in args.works.split(",") if x)
    rows = []
    for item in args.plys.split(","):
        lab, path = item.split("=", 1)
        xyz = read_ply(path)
        r = {"lab": lab, "n": len(xyz)}
        for s in sizes:
            r[f"vox{s}"] = occupied(xyz, s)
        d = knn_spread(xyz, sample=args.knn_sample)
        r["knn8_med"] = float(np.median(d))
        r["knn8_p90"] = float(np.percentile(d, 90))
        c = np.median(xyz, 0)
        r["r95"] = float(np.percentile(np.linalg.norm(xyz - c, axis=1), 95))
        if lab in works:
            mp = Path(works[lab]) / "metrics.json"
            if mp.exists():
                m = json.loads(mp.read_text())
                r["track_mean"] = m.get("track_mean")
                r["obs"] = m.get("obs")
                r["reproj"] = m.get("reproj")
        rows.append(r)

    base = rows[0]
    w = max(len(r["lab"]) for r in rows) + 1
    print(f"{'臂':<{w}} {'点数':>9} " + " ".join(f"{'占据'+str(s)+'m':>11}" for s in sizes)
          + f" {'点/格':>7} {'k近邻中位':>10} {'轨迹均值':>9} {'重投影':>8}")
    for r in rows:
        dens = r["n"] / max(r[f"vox{sizes[1]}"], 1)
        print(f"{r['lab']:<{w}} {r['n']:>9,} "
              + " ".join(f"{r[f'vox{s}']:>11,}" for s in sizes)
              + f" {dens:>7.2f} {r['knn8_med']:>10.4f}"
              + f" {r.get('track_mean') or float('nan'):>9.2f}"
              + f" {r.get('reproj') or float('nan'):>8.4f}")
    print()
    print(f"相对 {base['lab']}(>1 = 覆盖更大 / 更散):")
    for r in rows[1:]:
        cov = " ".join(f"{s}m {r[f'vox{s}']/max(base[f'vox{s}'],1):.3f}×" for s in sizes)
        print(f"  {r['lab']:<{w}} 覆盖 {cov}   k近邻 {r['knn8_med']/base['knn8_med']:.3f}×"
              f"   点数 {r['n']/base['n']:.3f}×")


if __name__ == "__main__":
    main()
