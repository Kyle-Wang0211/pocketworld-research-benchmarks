#!/usr/bin/env python3
"""从完整 413 帧的 batch 目录切出一个**内部自洽**的子集。

⚠️ 为什么不能直接用 limit:邻居表按完整 413 帧算,子集里没有那些帧的深度 ⇒
   geom 一致性与 ConfidenceCompute 全部失真(实测 conf p50 掉到 0.048,
   即计数只有基数 1 —— 没有任何源视图被采信)。
   必须在子集内部重算邻居(仍用 COLMAP 式打分:共视 × 三角化角高斯)。
"""
import sys, os, json
import numpy as np

src = sys.argv[1]; dst = sys.argv[2]; stride = int(sys.argv[3]) if len(sys.argv)>3 else 3
R = os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks")
os.makedirs(dst, exist_ok=True)

meta = json.load(open(f"{src}/frames.json"))
NF, W, H, NSRC = meta["count"], meta["width"], meta["height"], meta["num_src"]
sel = list(range(0, NF, stride))
print(f"子集 {len(sel)} / {NF} 帧(stride={stride})")

z = np.load(f"{R}/tools/python/diffmvs_out/trio_model_lapa.npz", allow_pickle=True)
pts, oi, oo, C = z["pts"], z["obs_idx"], z["obs_off"], z["centers"]
sets = {f: set(oi[oo[f]:oo[f+1]].tolist()) for f in sel}

THETA0, SIGMA = 12.0, 8.0
neigh = np.zeros((len(sel), NSRC), np.int32)
angs = []
for i, f in enumerate(sel):
    sc = []
    for j, g in enumerate(sel):
        if g == f: continue
        common = sets[f] & sets[g]
        if len(common) < 100: continue
        X = pts[np.fromiter(common, np.int64)]
        v1 = X - C[f]; v2 = X - C[g]
        v1 /= np.linalg.norm(v1,axis=1,keepdims=True)+1e-12
        v2 /= np.linalg.norm(v2,axis=1,keepdims=True)+1e-12
        med = float(np.median(np.degrees(np.arccos(np.clip((v1*v2).sum(1),-1,1)))))
        sc.append((len(common)*np.exp(-((med-THETA0)**2)/(2*SIGMA**2)), med, j))
    sc.sort(reverse=True)
    picked = [j for _,_,j in sc[:NSRC]]
    # 邻居不足时用子集内最近的补齐(交付无损:宁可质量低不可缺帧)
    while len(picked) < NSRC:
        d = np.array([np.linalg.norm(C[g]-C[f]) if (g!=f and j not in picked) else 1e9
                      for j,g in enumerate(sel)])
        picked.append(int(np.argmin(d)))
    neigh[i] = picked            # ⚠️ 存的是**子集内下标**,不是原始帧号
    if sc: angs.append(np.median([a for _,a,_ in sc[:NSRC]]))
neigh.tofile(f"{dst}/neighbors.i32")
print(f"  中位三角化角 {np.median(angs):.2f}°  (p10 {np.percentile(angs,10):.2f}°)")

cams = np.fromfile(f"{src}/cams.f32", np.float32).reshape(NF,36)
cams[sel].tofile(f"{dst}/cams.f32")
imgs = np.memmap(f"{src}/images.f16", np.float16, "r").reshape(NF,H,W)
np.ascontiguousarray(imgs[sel]).tofile(f"{dst}/images.f16")
json.dump({**meta, "count": len(sel), "subset_of": src, "stride": stride,
           "orig_index": sel}, open(f"{dst}/frames.json","w"), ensure_ascii=False)
print(f"→ {dst}/  ({len(sel)} 帧)")
