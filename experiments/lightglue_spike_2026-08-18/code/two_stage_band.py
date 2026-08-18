#!/usr/bin/env python3
"""两级预算 coarse-to-fine:先用少量关键点自举几何,再把大预算限制在窄极线带内。

依据:
 · 文献 "SfM using Dense CNN Features":粗层匹配的对应转移到高分辨率层,
   新对应**只在受约束区域内**搜索。
 · 生产已出货同形状:[GUIDED-TEMPORAL] raw Lowe 匹配 → TVG 出 E/F 种子 →
   极线带内引导重匹配 → 重新 TVG,**只在严格支配原始内点数时才采纳**(天然无损)。

为什么比我先前量的 ARKit 极线带更强:那次带宽必须 34px 才能吸收 ARKit 0.5° 的
旋转误差(带内 1.79%);自举出来的 E 是从**本对图像自己的匹配**估的,精度高一个量级,
带宽可以收到 ~10px(带内 0.53%)⇒ 交叉注意力那一侧再快约 3.4×。

本脚本量的是:用重建位姿(代表"自举后的高精度几何")vs ARKit 级误差,
带内候选比例各是多少,以及折算到整体的倍数。
⚠️ 只量上限,不改匹配 —— 真无损与否要看重建层。
"""
import argparse, sqlite3
import numpy as np

MAX_IMAGE_ID = 2147483647


def blob(b, dtype, cols):
    return np.frombuffer(b, dtype=dtype).reshape(-1, cols)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--poses", required=True)
    ap.add_argument("--pairs", type=int, default=120)
    ap.add_argument("--q-sample", type=int, default=400)
    ap.add_argument("--rot-noise-deg", type=float, default=0.0,
                    help="给位姿注入旋转噪声,模拟 ARKit 精度(0=重建级精度)")
    ap.add_argument("--bands", default="4,6,10,20,34")
    args = ap.parse_args()

    z = np.load(args.poses)
    idx = {int(i): k for k, i in enumerate(z["ids"])}
    K, R, t = z["K"], z["R"].copy(), z["t"]

    if args.rot_noise_deg > 0:
        rng0 = np.random.default_rng(1)
        for i in range(len(R)):
            ax = rng0.standard_normal(3); ax /= np.linalg.norm(ax)
            th = np.deg2rad(args.rot_noise_deg)
            kx = np.array([[0,-ax[2],ax[1]],[ax[2],0,-ax[0]],[-ax[1],ax[0],0]])
            R[i] = (np.eye(3) + np.sin(th)*kx + (1-np.cos(th))*kx@kx) @ R[i]

    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    kps = {i: blob(d, np.float32, c)
           for i, c, d in db.execute("select image_id,cols,data from keypoints")}
    pairs = [p for (p,) in db.execute("select pair_id from matches order by pair_id")]
    db.close()
    step = max(1, len(pairs) // args.pairs)
    pairs = pairs[::step][:args.pairs]

    bands = [float(b) for b in args.bands.split(",")]
    rng = np.random.default_rng(0)
    frac = {b: [] for b in bands}
    n = 0
    for pid in pairs:
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        a, b_ = idx.get(i1), idx.get(i2)
        if a is None or b_ is None or i1 not in kps or i2 not in kps: continue
        x1, x2 = kps[i1][:, :2].astype(np.float64), kps[i2][:, :2].astype(np.float64)
        if len(x1) < 10 or len(x2) < 10: continue
        R12 = R[b_] @ R[a].T
        t12 = t[b_] - R12 @ t[a]
        tx = np.array([[0,-t12[2],t12[1]],[t12[2],0,-t12[0]],[-t12[1],t12[0],0]])
        F = np.linalg.inv(K[b_]).T @ (tx @ R12) @ np.linalg.inv(K[a])
        sel = rng.choice(len(x1), min(args.q_sample, len(x1)), replace=False)
        h1 = np.concatenate([x1[sel], np.ones((len(sel),1))], 1)
        lines = h1 @ F.T
        nrm = np.sqrt(lines[:,0]**2 + lines[:,1]**2) + 1e-12
        h2 = np.concatenate([x2, np.ones((len(x2),1))], 1)
        dist = np.abs(lines @ h2.T) / nrm[:,None]
        for bd in bands: frac[bd].append((dist < bd).mean())
        n += 1

    tag = "重建级几何(自举后)" if args.rot_noise_deg == 0 else f"注入 {args.rot_noise_deg}° 旋转噪声(ARKit 级)"
    print(f"{tag} —— {n} 对")
    print(f"{'带宽px':>8} {'带内比例':>10} {'交叉侧省':>10} {'整体(交叉占1/3)':>16}")
    for bd in bands:
        f = float(np.mean(frac[bd]))
        cross = 1/max(f,1e-9)
        overall = 3.0 / (2.0 + 1.0/cross)
        print(f"{bd:>8.0f} {f*100:>9.2f}% {cross:>9.1f}× {overall:>15.3f}×")


if __name__ == "__main__":
    main()
