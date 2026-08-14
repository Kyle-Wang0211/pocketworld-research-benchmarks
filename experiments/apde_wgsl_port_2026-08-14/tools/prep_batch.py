#!/usr/bin/env python3
"""414 帧批量的预处理:一次性解码 + 相机表 + 邻居表。

产出(供 C++ 批量跑用):
    images.f16    (N, 512, 896) 灰度,f16     ← 一次解码,后面反复用
    cams.f32      (N, 36) float,每帧 K9+R9+t3+c3+dmin/dmax+w/h 打平
    neighbors.i32 (N, 4)  每帧的 4 个源视图索引
    frames.json   帧序、名字、深度范围

⚠️ 分辨率:非等比缩到 896×512(K 已编码,见 make_fixture.py 的说明)。
⚠️ 邻居用 COLMAP 式打分(共视 × 三角化角高斯)——
   纯按共视排会选到基线 4cm/视差角 0.6° 的近重复帧,深度完全没约束。
"""
import sys, os, json
import numpy as np
from PIL import Image

R = os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks")
MODEL = f"{R}/tools/python/diffmvs_out/trio_model_lapa.npz"
PHOTOS = (f"{R}/data/official_da3_base_k35_strict_seq_2026_06_02/"
          f"capture_seq_k35_strict/photos_highres")
W, H, NSRC = 896, 512, 4
THETA0, SIGMA = 12.0, 8.0


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "/tmp/apde_batch"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0   # 0 = 全部
    os.makedirs(out, exist_ok=True)

    z = np.load(MODEL, allow_pickle=True)
    names, K, w2c, centers = z["names"], z["K"], z["w2c"], z["centers"]
    pts, oi, oo = z["pts"], z["obs_idx"], z["obs_off"]
    N = len(names) if not limit else min(limit, len(names))
    print(f"帧数 {N}")

    # ── 观测集合(算共视与三角化角用)──
    sets = [set(oi[oo[f]:oo[f + 1]].tolist()) for f in range(len(names))]

    # ── 邻居表 + 深度范围 ──
    neigh = np.zeros((N, NSRC), np.int32)
    drange = np.zeros((N, 2), np.float32)
    angs_all = []
    for f in range(N):
        Cr = centers[f]
        sc = []
        for g in range(len(names)):
            if g == f:
                continue
            common = sets[f] & sets[g]
            if len(common) < 200:
                continue
            X = pts[np.fromiter(common, np.int64)]
            v1 = X - Cr; v2 = X - centers[g]
            v1 /= np.linalg.norm(v1, axis=1, keepdims=True) + 1e-12
            v2 /= np.linalg.norm(v2, axis=1, keepdims=True) + 1e-12
            med = float(np.median(np.degrees(np.arccos(
                np.clip((v1 * v2).sum(1), -1, 1)))))
            sc.append((len(common) * np.exp(-((med - THETA0) ** 2) / (2 * SIGMA ** 2)),
                       med, g))
        sc.sort(reverse=True)
        # ⚠️ 邻居不足时用最近的补齐,避免整帧作废(交付无损:宁可质量低不可缺帧)
        picked = [g for _, _, g in sc[:NSRC]]
        while len(picked) < NSRC:
            d = np.linalg.norm(centers[:len(names)] - Cr, axis=1)
            d[f] = 1e9
            for p in picked:
                d[p] = 1e9
            picked.append(int(np.argmin(d)))
        neigh[f] = picked
        if sc:
            angs_all.append(np.median([a for _, a, _ in sc[:NSRC]]))

        idx = oi[oo[f]:oo[f + 1]]
        Xc = (w2c[f][:3, :3] @ pts[idx].T).T + w2c[f][:3, 3]
        d = Xc[:, 2]; d = d[d > 0]
        lo, hi = np.percentile(d, [1, 99])
        drange[f] = (lo * 0.9, hi * 1.1)
        if f % 100 == 0:
            print(f"  邻居/深度范围 {f}/{N}", flush=True)
    neigh.tofile(f"{out}/neighbors.i32")
    print(f"  中位三角化角 {np.median(angs_all):.2f}°  "
          f"(p10 {np.percentile(angs_all,10):.2f}° p90 {np.percentile(angs_all,90):.2f}°)")

    # ── 相机表(36 float/帧,与 C++ 侧约定一致)──
    cams = np.zeros((N, 36), np.float32)
    for f in range(N):
        Rm = w2c[f][:3, :3]; t = w2c[f][:3, 3]
        cams[f, 0:9] = K[f].reshape(-1)
        cams[f, 9:18] = Rm.reshape(-1)
        cams[f, 18:21] = t
        cams[f, 21:24] = centers[f]
        cams[f, 24] = drange[f, 0]; cams[f, 25] = drange[f, 1]
        cams[f, 26] = W; cams[f, 27] = H
    cams.tofile(f"{out}/cams.f32")

    # ── 图像:一次解码,非等比缩放 ──
    imgs = np.zeros((N, H, W), np.float16)
    for f in range(N):
        im = Image.open(f"{PHOTOS}/{names[f]}").convert("L").resize((W, H), Image.BILINEAR)
        imgs[f] = (np.asarray(im, np.float32) / 255.0).astype(np.float16)
        if f % 50 == 0:
            print(f"  解码 {f}/{N}", flush=True)
    imgs.tofile(f"{out}/images.f16")

    json.dump({"count": int(N), "width": W, "height": H, "num_src": NSRC,
               "names": [str(x) for x in names[:N]],
               "drange": drange.tolist()},
              open(f"{out}/frames.json", "w"), ensure_ascii=False)
    print(f"→ {out}/  images.f16({imgs.nbytes/1e6:.0f}MB) cams.f32 neighbors.i32 frames.json")


if __name__ == "__main__":
    main()
