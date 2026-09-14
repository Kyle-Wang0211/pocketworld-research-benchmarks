#!/usr/bin/env python3
"""官方768 + 官方几何门(>=3视图/1px/1%) + 纹理门(无纹理区直接不输出)。
目标由用户重定义:白墙粘连 = 瞎造的几何 => 不知道就别输出, 没有墙也行。
纹理门只用图像本身判定,不碰几何:局部方差低 => 该像素的匹配代价曲线是平的 => 丢弃。
输出两版供肉眼对照:仅几何门 / 几何门+纹理门。"""
import os, sys, glob
import numpy as np, cv2
sys.path.insert(0, "/root/diffmvs")
from filter import check_geometric_consistency
from datasets.data_io import read_pfm

D = "/root/out_official"
WIN = 11          # 与 COLMAP PatchMatch 默认窗口同量级(window_radius 5 => 11x11)
def read_cam(p):
    L = [l.rstrip() for l in open(p)]
    E = np.fromstring(" ".join(L[1:5]), dtype=np.float64, sep=" ").reshape(4, 4)
    K = np.fromstring(" ".join(L[7:10]), dtype=np.float64, sep=" ").reshape(3, 3)
    return K, E

def local_std(gray):
    g = gray.astype(np.float32) / 255.0
    m = cv2.blur(g, (WIN, WIN))
    m2 = cv2.blur(g * g, (WIN, WIN))
    return np.sqrt(np.clip(m2 - m * m, 0, None))

raw, tex = {}, {}
for f in sorted(glob.glob(f"{D}/depth_est/*.pfm")):
    i = int(os.path.basename(f)[:8])
    d = np.array(read_pfm(f)[0], dtype=np.float32)
    K, E = read_cam(f"{D}/cams/{i:08d}_cam.txt")
    raw[i] = (d, K, E)
    img = cv2.resize(cv2.imread(f"{D}/images/{i:08d}.jpg"), (d.shape[1], d.shape[0]), interpolation=cv2.INTER_AREA)
    tex[i] = (local_std(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)), img)
allstd = np.concatenate([t[0].ravel()[::17] for t in tex.values()])
print("局部标准差分布(11x11, 灰度归一到[0,1]):",
      " ".join(f"p{q}={np.percentile(allstd,q):.4f}" for q in (5,10,20,30,50)), flush=True)

lines = [l.strip() for l in open("/root/mvs_P16k/pair.txt") if l.strip()]
n = int(lines[0]); pairs = []; k = 1
for _ in range(n):
    ref = int(lines[k]); t = lines[k+1].split(); m = int(t[0])
    pairs.append((ref, [int(t[1+2*j]) for j in range(m)][:10])); k += 2

TEX_T = float(os.environ.get("TEX_T", "0.02"))
for tag, use_tex in (("geo", False), ("geotex", True)):
    OUT = f"/root/regionmerge/gated_off768_{tag}"
    for s in ("depth", "color", "cam"): os.makedirs(f"{OUT}/{s}", exist_ok=True)
    kept = []
    for ref, srcs in pairs:
        if ref not in raw: continue
        dref, Kr, Er = raw[ref]
        gsum = np.zeros(dref.shape, np.int32); rsum = np.zeros(dref.shape, np.float32)
        for s in srcs:
            if s not in raw: continue
            ds, Ks, Es = raw[s]
            gm, dr, _, _ = check_geometric_consistency(dref, Kr, Er, ds, Ks, Es, 30.0, 0.3, 1.0, 0.01)
            gsum += gm.astype(np.int32); rsum += dr
        davg = (rsum + dref) / (gsum + 1)
        keep = (gsum >= 3) & (dref > 0)
        if use_tex: keep &= (tex[ref][0] >= TEX_T)
        kept.append(keep.mean())
        np.save(f"{OUT}/depth/{ref:08d}.npy", np.where(keep, davg, 0).astype(np.float32))
        cv2.imwrite(f"{OUT}/color/{ref:08d}.png", tex[ref][1])
        np.savez(f"{OUT}/cam/{ref:08d}.npz", K=Kr, E=Er)
    print(f"  {tag:<7} keep mean {np.mean(kept):.3f} | 全塌帧 {int((np.array(kept)==0).sum())}", flush=True)
print(f"纹理门阈值 TEX_T={TEX_T} (局部标准差,灰度[0,1])")
