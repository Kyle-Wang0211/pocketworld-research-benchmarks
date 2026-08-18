#!/usr/bin/env python3
"""先量再建:极线带排序后,FlexAttention 的 128×128 块能跳掉多少?

动机(来自 08-18 的算子级 profile):交叉注意力约占 fp16 总时间的 29%。用极线带做掩码
**不省算力**——SDPA 照样算满 N²,掩码只是把结果抹掉。要真省,必须让 kernel **跳过整块**,
这正是 FlexAttention 的 BlockMask 干的事。

但 BlockMask 的粒度是 128×128,而关键点顺序是任意的 ⇒ 随机顺序下每个 128 块都散布全图,
**没有任何块是全空的**,块稀疏度 = 0,白做。所以关键在排序:

  把两幅图的关键点都按「绕极点的极线角」排序 ⇒ 同一条极线上的点在两幅图里都聚成一段
  ⇒ 极线约束矩阵变成**带状**,带外的块整块为空。

⚠️ 排序本身是无损的:LightGlue 是集合 transformer,位置信息来自坐标不是下标,
   置换输入只会让输出同样置换(排完再置换回去)。这不是近似。

⚠️ 这个脚本**只量可行性**,不改模型。如果块存活率不够低(比如 >40%),这条路不值得建。
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, "LightGlue")
from lightglue import ALIKED
from lightglue.utils import load_image

BLK = 128   # FlexAttention 的块粒度


def epipolar_lines(K1, R1, t1, K2, R2, t2):
    """返回基础矩阵 F(把图1的点映成图2的线)与图1中的极点。"""
    R = R2 @ R1.T
    t = t2 - R @ t1
    tx = np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])
    E = tx @ R
    F = np.linalg.inv(K2).T @ E @ np.linalg.inv(K1)
    # 图1中的极点 = F 的右零空间
    _, _, vt = np.linalg.svd(F)
    e1 = vt[-1]
    return F, e1 / (e1[2] if abs(e1[2]) > 1e-9 else 1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--poses", default="poses_p16k.npz")
    ap.add_argument("--n", type=int, default=16384)
    ap.add_argument("--tol", type=float, default=3.0, help="极线带容差(像素)")
    ap.add_argument("--pairs", type=int, default=6)
    ap.add_argument("--start", type=int, default=0,
                    help="⚠️ 从 0 开始取会撞上序列开头的低纹理帧(只出 ~7.4k 点),\n不具代表性 —— 真实 @16384 的中位数是跑满 16384 的")
    a = ap.parse_args()

    z = np.load(a.poses)
    ids, K, R, t = z["ids"], z["K"], z["R"], z["t"]
    frames = sorted(Path("frames").glob("*.jpg"))
    dev = "cuda"
    ext = ALIKED(max_num_keypoints=a.n, detection_threshold=0.02).eval().to(dev)

    def kpts(i):
        img = load_image(str(frames[i])).to(dev)
        # 🔴 同 profile_lg.py:必须走 extract(resize=),否则缺 antialias,点数少 30-60%
        with torch.no_grad(), torch.autocast("cuda", torch.float16):
            f = ext.extract(img, resize=1600)
        return f["keypoints"][0].float()

    print(f"块粒度 {BLK}×{BLK}  带宽容差 {a.tol}px  关键点上限 {a.n}")
    print(f"{'配对':>10} {'点数':>13} {'点级存活':>9} {'块级(随机序)':>13} {'块级(极线排序)':>15}")
    rows = []
    for p in range(a.pairs):
        i, j = a.start + p, a.start + p + 1
        x1, x2 = kpts(i), kpts(j)
        n1, n2 = len(x1), len(x2)
        F, e1 = epipolar_lines(K[i], R[i], t[i], K[j], R[j], t[j])
        Ft = torch.from_numpy(F).float().to(dev)

        h1 = torch.cat([x1, torch.ones(n1, 1, device=dev)], 1)
        h2 = torch.cat([x2, torch.ones(n2, 1, device=dev)], 1)
        lines = h1 @ Ft.T                                   # [n1,3] 每个点在图2里的极线
        nrm = lines[:, :2].norm(dim=1, keepdim=True).clamp_min(1e-9)
        d = (lines @ h2.T).abs() / nrm                      # [n1,n2] 点到线的像素距离
        mask = d < a.tol
        pt_keep = mask.float().mean().item()

        def block_density(m):
            n1p = (m.shape[0] + BLK - 1) // BLK * BLK
            n2p = (m.shape[1] + BLK - 1) // BLK * BLK
            pad = torch.zeros(n1p, n2p, dtype=torch.bool, device=dev)
            pad[:m.shape[0], :m.shape[1]] = m
            blk = pad.view(n1p // BLK, BLK, n2p // BLK, BLK).any(3).any(1)
            return blk.float().mean().item()

        rand_blk = block_density(mask)
        # 按绕极点的极线角排序两幅图
        ang1 = torch.from_numpy(
            np.arctan2(x1[:, 1].cpu().numpy() - e1[1],
                       x1[:, 0].cpu().numpy() - e1[0])).to(dev)
        o1 = ang1.argsort()
        # 图2 按对应极线在图2中的方向角排序(用 F 映过去的线的法向角)
        l2 = h2 @ torch.linalg.inv(Ft).T          # 图2的点映回图1的线 → 同一束
        ang2 = torch.atan2(l2[:, 1], l2[:, 0])
        o2 = ang2.argsort()
        sort_blk = block_density(mask[o1][:, o2])

        rows.append((pt_keep, rand_blk, sort_blk))
        print(f"{i:>4}-{j:<5} {n1:>6}×{n2:<6} {pt_keep*100:>8.2f}% "
              f"{rand_blk*100:>12.1f}% {sort_blk*100:>14.1f}%")

    r = np.array(rows)
    print(f"\n均值      点级 {r[:,0].mean()*100:.2f}%   "
          f"块级随机序 {r[:,1].mean()*100:.1f}%   块级极线排序 {r[:,2].mean()*100:.1f}%")
    gain = 1.0 / max(r[:, 2].mean(), 1e-6)
    print(f"⇒ 交叉注意力理论上限 {gain:.2f}×;交叉占 fp16 总时长约 29% "
          f"⇒ 整体上限 {1/(1-0.29+0.29*r[:,2].mean()):.3f}×")


if __name__ == "__main__":
    main()
