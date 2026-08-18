#!/usr/bin/env python3
"""入口删点:在**进第 0 层之前**用几何删关键点,让自注意力也一起省(N² 全额)。

为什么这是新的:我先前把极线约束用成**交叉注意力的稀疏掩码**,只值 1.49×
—— 因为交叉只占每层 1/3,阿姆达尔卡死。正确用法是在入口就把点删掉,
自注意力(2/3)跟着一起省。

为什么有空间:实测剪枝的点数曲线**第 2 层后就躺平在 67%**(层0 97%→层6 67%),
而剪枝靠的是学出来的 matchability,**它不知道几何**;极线带内候选只占 1.79%,
几何能砍的远比它多。

判据:一个图1的关键点,若其极线带内**图2的关键点少于 min-cand 个**,
它在几何上不可能匹配 ⇒ 删。这不是近似,是排除不可能。
"""
import argparse, sqlite3
import numpy as np

MAX_IMAGE_ID = 2147483647


def blob(b, dtype, cols):
    return np.frombuffer(b, dtype=dtype).reshape(-1, cols)


def fundamental(K, R, t, a, b):
    R12 = R[b] @ R[a].T
    t12 = t[b] - R12 @ t[a]
    tx = np.array([[0,-t12[2],t12[1]],[t12[2],0,-t12[0]],[-t12[1],t12[0],0]])
    return np.linalg.inv(K[b]).T @ (tx @ R12) @ np.linalg.inv(K[a])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--poses", required=True)
    ap.add_argument("--pairs", type=int, default=80)
    ap.add_argument("--band", type=float, default=34.0)
    ap.add_argument("--min-cands", default="1,2,4,8")
    args = ap.parse_args()

    z = np.load(args.poses)
    idx = {int(i): k for k, i in enumerate(z["ids"])}
    K, R, t = z["K"], z["R"], z["t"]
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    kps = {i: blob(d, np.float32, c)
           for i, c, d in db.execute("select image_id,cols,data from keypoints")}
    pairs = [p for (p,) in db.execute("select pair_id from matches order by pair_id")]
    db.close()
    step = max(1, len(pairs)//args.pairs); pairs = pairs[::step][:args.pairs]

    mins = [int(x) for x in args.min_cands.split(",")]
    keep = {m: [] for m in mins}
    n = 0
    for pid in pairs:
        i1, i2 = pid//MAX_IMAGE_ID, pid%MAX_IMAGE_ID
        a, b = idx.get(i1), idx.get(i2)
        if a is None or b is None or i1 not in kps or i2 not in kps: continue
        x1, x2 = kps[i1][:, :2].astype(np.float64), kps[i2][:, :2].astype(np.float64)
        F = fundamental(K, R, t, a, b)
        h1 = np.concatenate([x1, np.ones((len(x1),1))], 1)
        h2 = np.concatenate([x2, np.ones((len(x2),1))], 1)
        cnt = np.zeros(len(x1), dtype=np.int32)
        B = 2048
        for s in range(0, len(x1), B):
            L = h1[s:s+B] @ F.T
            nrm = np.sqrt(L[:,0]**2 + L[:,1]**2) + 1e-12
            d = np.abs(L @ h2.T) / nrm[:,None]
            cnt[s:s+B] = (d < args.band).sum(1)
        for m in mins:
            keep[m].append((cnt >= m).mean())
        n += 1

    print(f"{n} 对,带宽 {args.band:.0f}px(ARKit 口径),起始 {len(x1)} 点/图")
    print(f"{'最少候选数':>10} {'保留点比例':>10} {'N² 省':>8} {'⇒ 整体':>8}")
    for m in mins:
        f = float(np.mean(keep[m]))
        print(f"{m:>10} {f*100:>9.1f}% {1/f**2:>7.2f}× {1/f**2:>7.2f}×")
    print("\n注:入口删点让自注意力+交叉注意力一起省,所以 N² 的收益是全额的,")
    print("    不像稀疏掩码只作用在交叉那 1/3 上。")


if __name__ == "__main__":
    main()
