#!/usr/bin/env python3
"""上游前端到底通过什么影响 CasDiffMVS?——把三条通道逐条对拍。

依据 tools/python/diffmvs/colmap_input.py:CasDiffMVS **看不到点云**,SfM 只通过三样
东西影响它:
  ① 位姿 + 内参
  ② depth_min/max = 该视图可见稀疏点深度的 1%/99% 分位(colmap_input.py:368-371)
  ③ pair.txt   = 共视稀疏点三角化角套 theta0=5° 高斯求和,取 top-N(:374-390,:417-418)

⇒ 稀疏点是以**统计量**进入下游的,不是几何。那么"点更多"对下游的边际价值就取决于
   这三条通道对点数有多敏感 —— 这正是本脚本要量的。

⚠️ 位姿必须先做 Sim3 gauge 对齐再比:两次独立增量建图的尺度/朝向/原点本就是任意的。
"""
import argparse
import numpy as np
import pycolmap as pc

THETA0, SIGMA1, SIGMA2 = 5.0, 1.0, 10.0     # 与 colmap_input.py 的默认值一致


def load(work):
    # downstream.py 写的是 sparse/0(COLMAP 的多模型布局),裸 sparse/ 是空壳
    from pathlib import Path as _P
    d = _P(work) / "sparse" / "0"
    if not (d / "points3D.bin").exists():
        d = _P(work) / "sparse"
    rec = pc.Reconstruction(str(d))
    by_name = {}
    for iid, im in rec.images.items():
        by_name[im.name] = iid
    return rec, by_name


def centers(rec, order):
    """相机光心,按给定 image name 顺序。"""
    out = []
    for nm in order:
        im = rec.images[rec.find_image_with_name(nm).image_id]
        out.append(np.array(im.cam_from_world().inverse().translation))
    return np.stack(out)


def umeyama(src, dst):
    """相似变换 src→dst,返回 (s, R, t)。"""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    S, D = src - mu_s, dst - mu_d
    C = D.T @ S / len(src)
    U, sig, Vt = np.linalg.svd(C)
    F = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        F[2, 2] = -1
    R = U @ F @ Vt
    s = (sig * np.diag(F)).sum() / (S ** 2).sum() * len(src)
    return s, R, mu_d - s * R @ mu_s


def depth_range(rec, nm):
    """复刻 colmap_input.py 的深度范围口径:可见稀疏点深度的 1%/99% 分位。"""
    im = rec.images[rec.find_image_with_name(nm).image_id]
    cfw = im.cam_from_world()
    R, t = np.array(cfw.rotation.matrix()), np.array(cfw.translation)
    zs = []
    for p2d in im.points2D:
        if not p2d.has_point3D():
            continue
        X = np.array(rec.points3D[p2d.point3D_id].xyz)
        zs.append((R @ X + t)[2])
    if len(zs) < 10:
        return None
    zs = np.sort(np.array(zs))
    return zs[int(len(zs) * .01)], zs[int(len(zs) * .99)]


def view_scores(rec, order, top):
    """复刻 colmap_input.py 的 calc_score:共视点三角化角的高斯和。

    ⚠️ 必须向量化:朴素双层循环是 23.8 万点 × ~15 个共视对的纯 Python,跑不完。
       这里把每个 point3D 的观测展开成 (i,j) 对后一次性算完。
    """
    ids = [rec.find_image_with_name(nm).image_id for nm in order]
    pos = {i: k for k, i in enumerate(ids)}
    n = len(ids)
    C = np.zeros((n, 3))
    for i in ids:
        C[pos[i]] = np.array(rec.images[i].cam_from_world().inverse().translation)

    ii, jj, XX = [], [], []
    for _pid, p3 in rec.points3D.items():
        seen = [pos[e.image_id] for e in p3.track.elements if e.image_id in pos]
        if len(seen) < 2:
            continue
        x = np.array(p3.xyz)
        for a in range(len(seen)):
            for b in range(a + 1, len(seen)):
                ii.append(seen[a]); jj.append(seen[b]); XX.append(x)
    if not ii:
        return np.zeros((n, n)), [set() for _ in range(n)]
    ii = np.array(ii); jj = np.array(jj); XX = np.stack(XX)

    v1 = C[ii] - XX
    v2 = C[jj] - XX
    cos = (v1 * v2).sum(1) / (np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1) + 1e-12)
    th = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    sg = np.where(th <= THETA0, SIGMA1, SIGMA2)
    w = np.exp(-((th - THETA0) ** 2) / (2 * sg ** 2))

    S = np.zeros((n, n))
    np.add.at(S, (ii, jj), w)
    np.add.at(S, (jj, ii), w)
    sel = [set(np.argsort(S[i])[::-1][:top].tolist()) for i in range(n)]
    return S, sel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True, help="参照臂工作目录")
    ap.add_argument("--b", required=True, help="对比臂工作目录")
    ap.add_argument("--top", type=int, default=10, help="num_src_images,生产用 10")
    args = ap.parse_args()

    ra, na = load(args.a)
    rb, nb = load(args.b)
    common = sorted(set(na) & set(nb))
    print(f"共同帧 {len(common)}(A {len(na)} / B {len(nb)})")

    # ---- 通道①:位姿 ----
    Ca, Cb = centers(ra, common), centers(rb, common)
    s, R, t = umeyama(Cb, Ca)
    Cb_al = (s * (R @ Cb.T).T + t)
    d = np.linalg.norm(Cb_al - Ca, axis=1)
    scene = np.percentile(np.linalg.norm(Ca - Ca.mean(0), axis=1), 95)
    ang = []
    for nm in common:
        Ra = np.array(ra.images[ra.find_image_with_name(nm).image_id].cam_from_world().rotation.matrix())
        Rb = np.array(rb.images[rb.find_image_with_name(nm).image_id].cam_from_world().rotation.matrix())
        dR = Ra @ (Rb @ R.T).T
        ang.append(np.degrees(np.arccos(np.clip((np.trace(dR) - 1) / 2, -1, 1))))
    ang = np.array(ang)
    print(f"\n① 位姿   光心偏差 中位 {np.median(d)/scene*100:.3f}% 场景半径  "
          f"p95 {np.percentile(d,95)/scene*100:.3f}%")
    print(f"          朝向偏差 中位 {np.median(ang):.4f}°  p95 {np.percentile(ang,95):.4f}°")

    # ---- 通道②:深度范围 ----
    rel_lo, rel_hi = [], []
    for nm in common:
        A, B = depth_range(ra, nm), depth_range(rb, nm)
        if A is None or B is None:
            continue
        rel_lo.append(abs(B[0] * s - A[0]) / max(abs(A[0]), 1e-9))
        rel_hi.append(abs(B[1] * s - A[1]) / max(abs(A[1]), 1e-9))
    print(f"\n② 深度范围(1%/99% 分位,已按 gauge 尺度 {s:.4f} 折算)")
    print(f"          depth_min 相对差 中位 {np.median(rel_lo)*100:.2f}%  p95 {np.percentile(rel_lo,95)*100:.2f}%")
    print(f"          depth_max 相对差 中位 {np.median(rel_hi)*100:.2f}%  p95 {np.percentile(rel_hi,95)*100:.2f}%")

    # ---- 通道③:源视图选择 ----
    _, sa = view_scores(ra, common, args.top)
    _, sb = view_scores(rb, common, args.top)
    ov = np.array([len(x & y) / args.top for x, y in zip(sa, sb)])
    print(f"\n③ 源视图选择(top-{args.top})")
    print(f"          重合率 均值 {ov.mean()*100:.1f}%  中位 {np.median(ov)*100:.1f}%  "
          f"最差 {ov.min()*100:.1f}%")
    print(f"          完全一致的参考视图 {(ov==1).sum()}/{len(ov)}")


if __name__ == "__main__":
    main()
