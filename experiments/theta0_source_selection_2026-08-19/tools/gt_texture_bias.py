#!/usr/bin/env python3
"""BlendedMVS 的真值在无纹理区可不可信?

🔴 立项(2026-08-19):BlendedMVS 官方流程 = 用商业 MVS 管线(Altizure)从照片重建
   带纹理网格 → 渲染成图和深度。**"真值"本身就是 MVS 的输出。**
   而我们的病灶恰恰是 MVS 在无纹理区自信地算错 ⇒ 怀疑训练真值在白墙上本身就错,
   网络只是学会复现它。若成立,换更大的 BlendedMVG 无用(错误只是更多份)。

⚠️ 渲染深度每像素只有一层,不会出现稠密云那种"第二面墙"。判据换成:
   **同一场景、同一平面上,真值在低纹理像素处是不是比高纹理像素更不平?**
   同一平面 ⇒ 几何被控住,唯一差别是纹理。
"""
import os, sys, glob, json
import numpy as np, cv2

REPO = os.environ.get("DIFFMVS_REPO", "/workspace/diffmvs")
sys.path.insert(0, REPO)
from datasets.data_io import read_pfm

rng = np.random.default_rng(20260819)


def read_cam(p):
    L = open(p).read().split()
    E = np.array(L[1:17], np.float64).reshape(4, 4)
    K = np.array(L[18:27], np.float64).reshape(3, 3)
    return E, K


def ransac_plane(pts, iters=800, tol=0.02):
    best = (0, (np.array([0., 0., 1.]), 0.))
    for _ in range(iters):
        s = pts[rng.choice(len(pts), 3, replace=False)]
        nv = np.cross(s[1]-s[0], s[2]-s[0]); L = np.linalg.norm(nv)
        if L < 1e-9: continue
        nv /= L; d = -nv @ s[0]
        c = int((np.abs(pts @ nv + d) < tol).sum())
        if c > best[0]: best = (c, (nv, d))
    return best


def main(root, scans, out):
    res = []
    for scan in scans:
        for dp in sorted(glob.glob(f"{root}/{scan}/rendered_depth_maps/*.pfm"))[:12]:
            i = os.path.basename(dp)[:8]
            ip = f"{root}/{scan}/blended_images/{i}.jpg"
            cp = f"{root}/{scan}/cams/{i}_cam.txt"
            if not (os.path.exists(ip) and os.path.exists(cp)): continue
            D, _ = read_pfm(dp); D = np.asarray(D, np.float64)
            img = cv2.imread(ip, cv2.IMREAD_GRAYSCALE)
            if img is None or img.shape != D.shape: continue
            _, K = read_cam(cp)
            gx = cv2.Sobel(img, cv2.CV_32F, 1, 0, 3); gy = cv2.Sobel(img, cv2.CV_32F, 0, 1, 3)
            tex = cv2.blur(np.sqrt(gx*gx + gy*gy), (15, 15))
            v = D > 0
            if v.sum() < 20000: continue
            yy, xx = np.nonzero(v); z = D[v]
            P = np.stack([(xx-K[0,2])/K[0,0]*z, (yy-K[1,2])/K[1,1]*z, z], 1)
            s = P[rng.choice(len(P), min(60000, len(P)), replace=False)]
            cnt, (nv, d) = ransac_plane(s)
            if cnt < 0.10*len(s): continue
            r = np.abs(P @ nv + d); on = r < 0.10
            if on.sum() < 5000: continue
            t = tex[v][on]; rr = r[on]
            lo, hi = np.percentile(t, [25, 75])
            a = rr[t <= lo]; b = rr[t >= hi]
            if len(a) < 500 or len(b) < 500: continue
            res.append(dict(scan=scan, frame=i, n_plane=int(on.sum()),
                            low_p50=float(np.median(a)*1000), low_p90=float(np.percentile(a,90)*1000),
                            hi_p50=float(np.median(b)*1000),  hi_p90=float(np.percentile(b,90)*1000)))
    if not res:
        print("  没找到合格样本"); return
    L50=np.array([r["low_p50"] for r in res]); H50=np.array([r["hi_p50"] for r in res])
    L90=np.array([r["low_p90"] for r in res]); H90=np.array([r["hi_p90"] for r in res])
    print(f"\n  合格样本 {len(res)} 帧(来自 {len(set(r['scan'] for r in res))} 个场景)")
    print(f"\n  {'':18}{'低纹理':>12}{'高纹理':>12}{'倍数':>9}")
    print(f"  到平面残差 p50 {np.median(L50):>10.2f}mm{np.median(H50):>10.2f}mm{np.median(L50)/np.median(H50):>8.2f}x")
    print(f"  到平面残差 p90 {np.median(L90):>10.2f}mm{np.median(H90):>10.2f}mm{np.median(L90)/np.median(H90):>8.2f}x")
    w=int((L50>H50).sum())
    print(f"\n  低纹理更差的帧: {w}/{len(res)} ({100*w/len(res):.0f}%)")
    print(f"  => {'*** 真值在无纹理区确实更不可信' if w>0.7*len(res) else '*** 没有系统性差异,怀疑被推翻'}")
    json.dump(res, open(out,"w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2].split(","), sys.argv[3])
