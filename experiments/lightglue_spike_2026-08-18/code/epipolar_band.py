#!/usr/bin/env python3
"""极线带内候选比例:量生产 guide_mode=1 那把刀用在 LightGlue 交叉注意力上的理论上限。

生产已出货 `aether_gpu_match_gemm_pairs_guided(guide_mode=1)` —— 用 E/F 极线带把
候选限制在极线附近。对暴力匹配它把 N² 降成 N×带内候选;对 LightGlue 的**交叉注意力**,
同样的约束可以变成稀疏掩码:query i 只需 attend 到图2中落在它极线带内的 key。

这不是近似:落在极线带外的对应**在几何上就是错的**,注意力本来就该给零权重。

⚠️ 带宽必须吸收位姿误差。生产端位姿来自 ARKit(拍摄期就有,不用等 SfM),
   旧账实测 ARKit 旋转误差 ~0.5°。在 4032px 宽、~60°FOV 上,0.5° ≈ 34px。
   所以带宽要扫到 34px 以上才是端上可用的口径;更窄的带只在"位姿来自重建"时成立。

口径:F = K2^-T [t]x R K1^-1;点 x2 到极线 l=F·x1 的距离 = |l·x2|/sqrt(la²+lb²)。
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
    ap.add_argument("--pairs", type=int, default=120, help="抽样配对数")
    ap.add_argument("--q-sample", type=int, default=400, help="每对抽多少个 query 点")
    ap.add_argument("--bands", default="2,5,10,20,34,50,80")
    args = ap.parse_args()

    z = np.load(args.poses)
    idx = {int(i): k for k, i in enumerate(z["ids"])}
    K, R, t = z["K"], z["R"], z["t"]

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
    n_used = 0

    for pid in pairs:
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        a, b_ = idx.get(i1), idx.get(i2)
        if a is None or b_ is None or i1 not in kps or i2 not in kps:
            continue
        x1 = kps[i1][:, :2].astype(np.float64)
        x2 = kps[i2][:, :2].astype(np.float64)
        if len(x1) < 10 or len(x2) < 10:
            continue
        # 相对位姿 1→2
        R12 = R[b_] @ R[a].T
        t12 = t[b_] - R12 @ t[a]
        tx = np.array([[0, -t12[2], t12[1]], [t12[2], 0, -t12[0]], [-t12[1], t12[0], 0]])
        E = tx @ R12
        F = np.linalg.inv(K[b_]).T @ E @ np.linalg.inv(K[a])

        sel = rng.choice(len(x1), min(args.q_sample, len(x1)), replace=False)
        h1 = np.concatenate([x1[sel], np.ones((len(sel), 1))], 1)      # [q,3]
        lines = h1 @ F.T                                                # [q,3]
        nrm = np.sqrt(lines[:, 0] ** 2 + lines[:, 1] ** 2) + 1e-12
        h2 = np.concatenate([x2, np.ones((len(x2), 1))], 1)             # [n2,3]
        dist = np.abs(lines @ h2.T) / nrm[:, None]                      # [q,n2]
        for bd in bands:
            frac[bd].append((dist < bd).mean())
        n_used += 1

    print(f"用了 {n_used} 对,每对抽 {args.q_sample} 个 query 点")
    print(f"{'带宽(原图px)':>12} {'带内候选比例':>12} {'⇒ 交叉注意力可省':>16}")
    for bd in bands:
        f = float(np.mean(frac[bd]))
        print(f"{bd:>12.0f} {f*100:>11.2f}% {1/max(f,1e-9):>15.1f}×")
    print()
    print("⚠️ 端上可用的口径要看 ≥34px 那几行(ARKit 旋转误差 ~0.5° ≈ 34px @4032宽)")


if __name__ == "__main__":
    main()
