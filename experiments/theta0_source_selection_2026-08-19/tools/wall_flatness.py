#!/usr/bin/env python3
"""大平面平整度 —— 专抓"翘起"的尺子。

🔴 立项(2026-08-19,用户当场推翻我的排名):
   我用点数/覆盖/局部粗糙度排名,把 C 排第一并写下"放弃 DTU 没有代价"。
   用户肉眼看到的是**墙面翘起**:C 与官方 dtu 明显翘,官方 blendmvg 完全不翘。
   那三把尺子对此**结构性失明**:
     点数/覆盖 —— 翘起的墙点一个不少、照样占体素,只是占错位置
     局部粗糙度(k=15 PCA)—— 量**邻域厚度**,平滑弯曲的墙和平墙读数一样
   ⇒ 缺陷是**全局形状**,尺子必须是全局的。

做法:场景里最大的平面结构(实测占 40% 点)当靶。
  ⚠️ 不做"地板/墙"的语义假设 —— 实测本场景未重力对齐,
     最大平面法向 [0.837,0.111,0.536],次大平面族与它夹角 66°,不垂直。
  ⚠️ 区域**只框一次**(用参考臂),四臂共用;否则每臂各自拟合各自的墙,
     翘起会被重新拟合吸收掉。
  判据:① 残差 RMS / p95 / >2cm 占比   ② **翘度** = 残差沿面内方向的斜率(mm/m)
        ③ 分段中位残差极差(抓非线性卷边)
"""
import argparse, json
import numpy as np

DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
rng = np.random.default_rng(20260819)


def load(p, sub=1):
    f = open(p, "rb"); n = None
    while True:
        l = f.readline()
        if l.startswith(b"element vertex"): n = int(l.split()[-1])
        if l.strip() == b"end_header": break
    rec = np.fromfile(f, dtype=DT, count=n)
    if sub > 1: rec = rec[::sub]
    return np.stack([rec["x"], rec["y"], rec["z"]], 1).astype(np.float64)


def ransac_plane(pts, iters=1200, tol=0.02):
    best = (0, (np.array([0., 0., 1.]), 0.))
    for _ in range(iters):
        s = pts[rng.choice(len(pts), 3, replace=False)]
        nv = np.cross(s[1]-s[0], s[2]-s[0]); L = np.linalg.norm(nv)
        if L < 1e-9: continue
        nv /= L; d = -nv @ s[0]
        c = int((np.abs(pts @ nv + d) < tol).sum())
        if c > best[0]: best = (c, (nv, d))
    return best


def refit(pts, nv, d, tol=0.05, rounds=4):
    for _ in range(rounds):
        m = np.abs(pts @ nv + d) < tol
        if m.sum() < 200: break
        q = pts[m]; c = q.mean(0)
        _, _, V = np.linalg.svd(q - c, full_matrices=False)
        nv = V[-1] / np.linalg.norm(V[-1]); d = -nv @ c
    return nv, d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--arms", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--sub", type=int, default=4)
    ap.add_argument("--band", type=float, default=0.30, help="平面两侧取多厚一层(米)")
    ap.add_argument("--skip-dominant", action="store_true",
                    help="先剔掉最大平面(通常是地板),再找次大平面=墙")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    arms = [x.split("=", 1) for x in a.arms.split(",")]

    xyz = load(f"{a.dir}/{dict(arms)[a.ref]}", a.sub)
    s = xyz[rng.choice(len(xyz), min(200000, len(xyz)), replace=False)]
    cnt, (nv, d) = ransac_plane(s)
    nv, d = refit(xyz[np.abs(xyz @ nv + d) < 0.10], nv, d)
    if a.skip_dominant:
        # 实测本场景最大平面是地板(7.3×4.7m),翘起发生在与它成 66° 的次大平面上
        keep = xyz[np.abs(xyz @ nv + d) > 0.20]
        s2 = keep[rng.choice(len(keep), min(200000, len(keep)), replace=False)]
        cnt, (nv, d) = ransac_plane(s2)
        nv, d = refit(keep[np.abs(keep @ nv + d) < 0.10], nv, d)
        xyz = keep
    inl = xyz[np.abs(xyz @ nv + d) < a.band]
    ctr = inl.mean(0)
    _, _, V = np.linalg.svd(inl - ctr, full_matrices=False)
    e1, e2 = V[0], V[1]
    b1 = np.percentile((inl-ctr) @ e1, [2, 98]); b2 = np.percentile((inl-ctr) @ e2, [2, 98])
    print(f"  靶平面(参考臂 {a.ref}): {len(inl):,} 点 · 法向 {nv.round(3)} · "
          f"面内范围 {b1[1]-b1[0]:.2f} × {b2[1]-b2[0]:.2f} m")
    del xyz, inl, s

    print(f"\n{'臂':<12}{'面上点数':>11}{'残差RMS':>10}{'p95':>9}{'>2cm':>8}{'翘度':>11}{'分段极差':>10}")
    res = {}
    for lab, fn in arms:
        p = load(f"{a.dir}/{fn}", a.sub)
        t = p - ctr
        m = (np.abs(p @ nv + d) < a.band) & (t@e1 > b1[0]) & (t@e1 < b1[1]) \
            & (t@e2 > b2[0]) & (t@e2 < b2[1])
        w = p[m]
        if len(w) < 2000:
            print(f"  {lab:<10} 点太少 {len(w)}"); del p; continue
        nv_i, d_i = refit(w, nv, d)          # 每臂各自稳健拟合,不偏袒
        r = w @ nv_i + d_i
        u = (w - ctr) @ e1
        slope = np.linalg.lstsq(np.vstack([u, np.ones_like(u)]).T, r, rcond=None)[0][0]
        bins = np.percentile(u, np.linspace(0, 100, 11))
        med = [np.median(r[(u >= bins[i]) & (u < bins[i+1])]) for i in range(10)]
        res[lab] = dict(n=len(w), rms=float(np.sqrt((r**2).mean())*1000),
                        p95=float(np.percentile(np.abs(r), 95)*1000),
                        gt2cm=float((np.abs(r) > 0.02).mean()*100),
                        slope=float(abs(slope)*1000),
                        span=float((np.nanmax(med)-np.nanmin(med))*1000))
        v = res[lab]
        print(f"  {lab:<10}{v['n']:>11,}{v['rms']:>9.1f}mm{v['p95']:>8.1f}mm"
              f"{v['gt2cm']:>7.1f}%{v['slope']:>9.2f}mm/m{v['span']:>9.1f}mm")
        del p, w
    if a.out: json.dump(res, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
