#!/usr/bin/env python3
"""SARA 式配对打分:在调用昂贵匹配器**之前**,用位姿算「重叠 × 视差」。

依据(SARA, arXiv 2601.06831):学习式匹配器产出丰富对应,**但不是所有配对都对重建
有贡献**——冗余的近重复配对(视差太小,三角化病态)和低重叠配对消耗算力却几乎不增加
几何价值。所以在匹配之前按"重建信息量"排序,砍掉低分的。

为什么这条对我们是量级级别的:配对数**线性**决定端上总匹配耗时,而 LightGlue 单对
1.38 TFLOP(8192档)。kernel 优化只有 1.8×,砍配对是砍多少省多少。

⚠️ 与我上一次失败的削减的区别(那次丢了 11 帧,踩了「永久缺帧绝对禁止」红线):
   ① 判据从"匹配数"换成"几何信息量"——匹配数多但视差小的对,对三角化是废的;
   ② **每帧保底 k 条边**,用并查集确保配对图连通,结构上不可能丢帧。

⚠️ 位姿来源:实验用重建位姿;生产端等价物 = ARKit 位姿(拍摄期本来就有,
   而且生产已经在用它做空间序选对)。ARKit 位姿更糙,所以打分要留余量。
"""
import argparse, collections, shutil, sqlite3

import numpy as np

MAX_IMAGE_ID = 2147483647


def load_poses(npz):
    z = np.load(npz)
    idx = {int(i): k for k, i in enumerate(z["ids"])}
    return idx, z["K"], z["R"], z["t"], z["dlo"], z["dhi"], z["wh"]


def pair_geometry(a, b, K, R, t, dlo, dhi, wh, n_grid=8):
    """返回 (重叠比例, 视差角°)。重叠=图a的网格点在中位深度处投进图b的比例。"""
    Ka, Ra, ta = K[a], R[a], t[a]
    Kb, Rb, tb = K[b], R[b], t[b]
    Wa, Ha = wh[a]; Wb, Hb = wh[b]
    Ca = -Ra.T @ ta
    Cb = -Rb.T @ tb

    us = np.linspace(0.5 / n_grid, 1 - 0.5 / n_grid, n_grid)
    uv = np.stack(np.meshgrid(us * Wa, us * Ha), -1).reshape(-1, 2)
    uv1 = np.concatenate([uv, np.ones((len(uv), 1))], 1)
    ray = uv1 @ np.linalg.inv(Ka).T
    ray /= np.linalg.norm(ray, axis=1, keepdims=True)

    d_med = float(np.sqrt(dlo[a] * dhi[a]))          # 几何中位深度
    X = (Ra.T @ (d_med * ray).T).T + Ca               # 世界点
    xc = X @ Rb.T + tb
    ok = xc[:, 2] > 1e-6
    uvb = xc[ok] / xc[ok, 2:3]
    uvb = uvb @ Kb.T
    inside = ((uvb[:, 0] >= 0) & (uvb[:, 0] < Wb) & (uvb[:, 1] >= 0) & (uvb[:, 1] < Hb))
    overlap = inside.sum() / len(uv)

    # 视差:两台相机对"共视区中心点"的张角
    if inside.any():
        Xc = X[ok][inside].mean(0)
    else:
        Xc = X.mean(0)
    v1 = Ca - Xc; v2 = Cb - Xc
    cosv = np.clip(v1 @ v2 / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9), -1, 1)
    return float(overlap), float(np.degrees(np.arccos(cosv)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--poses", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-frac", type=float, default=0.5, help="保留配对比例")
    ap.add_argument("--min-deg", type=float, default=2.0,
                    help="视差角低于此值的配对判为三角化病态(与生产的 tri-angle 门同源)")
    ap.add_argument("--guard-k", type=int, default=6,
                    help="每帧保底边数,防止丢帧(上次按匹配数砍丢了11帧)")
    args = ap.parse_args()

    idx, K, R, t, dlo, dhi, wh = load_poses(args.poses)
    db = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    pairs = [p for (p,) in db.execute("select pair_id from matches")]
    db.close()

    scored = []
    for pid in pairs:
        i1, i2 = pid // MAX_IMAGE_ID, pid % MAX_IMAGE_ID
        a, b = idx.get(i1), idx.get(i2)
        if a is None or b is None:
            scored.append((pid, i1, i2, 1e9)); continue     # 无位姿一律保留
        ov, deg = pair_geometry(a, b, K, R, t, dlo, dhi, wh)
        # 视差太小的对:三角化病态,匹配再多也换不到好几何 ⇒ 重罚
        s = ov * min(deg, 30.0) * (0.05 if deg < args.min_deg else 1.0)
        scored.append((pid, i1, i2, s))

    scored.sort(key=lambda x: -x[3])
    n_keep = int(len(scored) * args.keep_frac)
    keep = {p for p, _, _, _ in scored[:n_keep]}

    # 每帧保底:按分数从高到低补,直到每帧都有 guard_k 条边
    deg_cnt = collections.Counter()
    for p, i1, i2, _ in scored:
        if p in keep:
            deg_cnt[i1] += 1; deg_cnt[i2] += 1
    added = 0
    for p, i1, i2, _ in scored:
        if p in keep:
            continue
        if deg_cnt[i1] < args.guard_k or deg_cnt[i2] < args.guard_k:
            keep.add(p); deg_cnt[i1] += 1; deg_cnt[i2] += 1; added += 1

    shutil.copy(args.db, args.out)
    for suf in ("-wal", "-shm"):
        import pathlib; pathlib.Path(args.out + suf).unlink(missing_ok=True)
    o = sqlite3.connect(args.out)
    o.executemany("delete from matches where pair_id=?",
                  [(p,) for p, _, _, _ in scored if p not in keep])
    o.execute("delete from two_view_geometries"); o.commit()
    n_left = o.execute("select count(*) from matches").fetchone()[0]
    o.close()

    covered = len(deg_cnt)
    sc = np.array([s for _, _, _, s in scored])
    print(f"{args.out}: 保留 {n_left}/{len(scored)} 对({n_left/len(scored)*100:.0f}%),"
          f"保底补回 {added} 对")
    print(f"  覆盖 {covered} 帧(应为全部),每帧边数 最少 {min(deg_cnt.values())} "
          f"中位 {int(np.median(list(deg_cnt.values())))}")
    print(f"  分数 中位 {np.median(sc):.3f} p10 {np.percentile(sc,10):.3f}")


if __name__ == "__main__":
    main()
