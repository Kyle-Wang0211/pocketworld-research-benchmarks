# -*- coding: utf-8 -*-
"""按官方口径重建 pair.txt: num_view = min(20, len(images)-1)  (colmap2mvsnet_np2.py:418)

为什么要做:
  filter.py 的两个融合函数都【遍历 pair.txt 里的全部 src】, 没有任何 [:num_view] 截断
  (filter.py:166 / :382); 只有【推理】才截断 (datasets/mvs.py:134 src_views[:n_views-1])。
  官方数据每个 ref 给融合 20 个 src (实测 ETH3D office/delivery_area/kicker 全是 20),
  而我们 8 月那份 pair.txt 只有 10 个 =>
  自适应闸的绝对阈值(geo_mask_sum>=10, geo_mask_sums[i]>=i, i 到 10)对我们等于
  要求 10/10 全票, 对官方只是 10/20 半数。这是移植缺陷, 不是算法缺陷。

评分函数 calc_score 与选择逻辑【整段 import 官方文件】, 本脚本不重新实现任何一行。
🔴 我只改了一处资源参数: 进程数 32 -> 12, 避免抢训练的 CPU。评分结果与进程数无关。
"""
import os, sys, numpy as np, multiprocessing as mp
from functools import partial
sys.path.insert(0, "/root")
import colmap2mvsnet_np2 as C

SPARSE = sys.argv[1]; OUT = sys.argv[2]; REF = sys.argv[3]

class A:  theta0 = 5; sigma1 = 1; sigma2 = 10
cameras, images, points3d = C.read_model(SPARSE, ".bin")
n = len(images)
print("稀疏模型: %d 相机 / %d 图 / %d 点" % (len(cameras), n, len(points3d)), flush=True)

extrinsic = {}
for i in images:
    e = np.zeros((4, 4)); e[:3, :3] = C.qvec2rotmat(images[i].qvec)
    e[:3, 3] = images[i].tvec; e[3, 3] = 1
    extrinsic[i] = e

queue = [(i, j) for i in range(n) for j in range(i + 1, n)]
print("算 %d 个视图对的评分 (官方 calc_score)..." % len(queue), flush=True)
p = mp.Pool(processes=12)
res = p.map(partial(C.calc_score, images=images, points3d=points3d, args=A, extrinsic=extrinsic), queue)
p.close(); p.join()
score = np.zeros((n, n))
for i, j, s in res: score[i, j] = s; score[j, i] = s

num_view = min(20, n - 1)          # colmap2mvsnet_np2.py:418 逐字
view_sel = []
for i in range(n):
    ss = np.argsort(score[i])[::-1]
    view_sel.append([(k, score[i, k]) for k in ss[:num_view]])

with open(OUT, "w") as f:           # :443-448 逐字
    f.write('%d\n' % n)
    for i, sv in enumerate(view_sel):
        f.write('%d\n%d ' % (i, len(sv)))
        for iid, s in sv: f.write('%d %d ' % (iid, s))
        f.write('\n')
print("写出 %s  (每 ref %d 个 src)" % (OUT, num_view), flush=True)

# ---- 判据: 前 10 个必须与现有 pair.txt 逐字相同 ----
def rd(p):
    L = open(p).read().split('\n'); m = int(L[0]); o = []
    for i in range(m):
        fl = L[2 + 2 * i].split(); k = int(fl[0])
        o.append([int(fl[1 + 2 * j]) for j in range(k)])
    return o
old, new = rd(REF), rd(OUT)
assert len(old) == len(new), "ref 数不同"
bad = [i for i in range(len(old)) if old[i] != new[i][:len(old[i])]]
print("\n[判据] 前 %d 个 src 与现有 pair.txt 相同的 ref: %d / %d"
      % (len(old[0]), len(old) - len(bad), len(old)), flush=True)
if bad:
    print("  🔴 不一致的 ref(前 5 个): %s" % bad[:5])
    for i in bad[:2]:
        print("     ref %d 旧 %s" % (i, old[i]))
        print("     ref %d 新 %s" % (i, new[i][:len(old[i])]))
    print("  🔴 这说明稀疏模型或评分与 8 月那次不同 —— 不能当作纯扩展, 停下报告。")
else:
    print("  ✅ 132/132 全同 => 新表是旧表的【纯扩展】, 深度图完全有效。", flush=True)
