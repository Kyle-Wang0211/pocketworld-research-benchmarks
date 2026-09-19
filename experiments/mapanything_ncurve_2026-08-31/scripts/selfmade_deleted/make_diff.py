# [差异染色 2026-08-31] K=8 vs K=64 的云到云距离,按距离染色。
# 两臂点数不同(24.50M vs 23.92M,掩码不同)⇒ 无 1:1 对应,用 KD 树最近邻。
# 目的:分块的接缝在普通渲染下未必看得出,染色能直接定位。
import numpy as np, json
from pathlib import Path
from scipy.spatial import cKDTree
ref=np.load("compare/_raw_k64.npy")     # 基准
qry=np.load("compare/_raw_k8.npy")      # 待测
print(f"  基准 {len(ref):,d} 点   待测 {len(qry):,d} 点")
rng=np.random.default_rng(1)
# 基准建树用全量(精度),查询降采样到可视规模
tree=cKDTree(ref.astype(np.float64), balanced_tree=False, compact_nodes=False)
idx=rng.choice(len(qry), 1_500_000, replace=False); idx.sort()
q=qry[idx].astype(np.float64)
d,_=tree.query(q, k=1, workers=-1)
ext=float(np.linalg.norm(ref.max(0)-ref.min(0)))
print(f"  场景对角线 {ext:.2f}")
print(f"  云到云距离: 中位 {np.median(d):.5f}  p95 {np.percentile(d,95):.5f}  "
      f"p99.9 {np.percentile(d,99.9):.5f}  最大 {d.max():.4f}")
print(f"  中位/场景 = {np.median(d)/ext*100:.4f}%")
# 染色:0→蓝, hi→红(hi 取 p99,避免离群点吃掉整个色阶)
hi=float(np.percentile(d,99))
t=np.clip(d/max(hi,1e-9),0,1)
rgb=np.stack([(t*255), (np.zeros_like(t)), ((1-t)*255)],1).astype(np.uint8)
q.astype("<f4").tofile("compare/bin/diff.pos"); rgb.tofile("compare/bin/diff.col")
m=json.load(open("compare/meta.json"))
lo,hi3=q.min(0),q.max(0)
m["diff"]={"n":int(len(q)),"center":[float(x) for x in (lo+hi3)/2],
           "ext":[float(x) for x in (hi3-lo)],"med":[float(x) for x in np.median(q,0)],
           "radius":float(np.linalg.norm(np.percentile(q,90,axis=0)-np.median(q,0))),
           "d_median":float(np.median(d)),"d_p95":float(np.percentile(d,95)),
           "d_p99":hi,"d_max":float(d.max()),"scene_ext":ext}
json.dump(m,open("compare/meta.json","w"))
print(f"✅ B 页数据完成  色阶: 蓝=0 → 红={hi:.4f}(p99)")
