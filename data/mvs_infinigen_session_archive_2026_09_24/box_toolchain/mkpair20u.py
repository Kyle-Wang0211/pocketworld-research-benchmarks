# -*- coding: utf-8 -*-
"""并集 pair.txt: 旧的 10 个原样保留 + 按官方评分补到 20 个。

为什么不做官方那种整表重算:
  实测重算后前 10 个 0/132 与旧表相同 => 这份稀疏模型/评分版本与 8 月那次不同。
  而【深度图是用旧表的前 10 个算出来的】(mvs.py:134 src_views[:n_views-1]),
  整表换掉就等于深度图与 pair 表脱节, 除非重新推理(要抢训练的 GPU)。
  => 取并集: 旧 10 个一个不动(深度图完全有效) + 官方评分里的次优若干补到 20。
  融合对 src 是【求和】(geo_mask_sum += ...), 与顺序无关, 所以补在后面不影响任何东西。
🔴 这是混合方案, 不是官方原样重算。诚实标注。
"""
import os, sys, numpy as np, multiprocessing as mp
from functools import partial
sys.path.insert(0, "/root")
import colmap2mvsnet_np2 as C

SPARSE, REF, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
class A: theta0 = 5; sigma1 = 1; sigma2 = 10

SC = "/root/pair_score.npy"
cameras, images, points3d = C.read_model(SPARSE, ".bin")
n = len(images)
if os.path.exists(SC):
    score = np.load(SC); print("复用已算好的评分矩阵", flush=True)
else:
    extrinsic = {}
    for i in images:
        e = np.zeros((4,4)); e[:3,:3] = C.qvec2rotmat(images[i].qvec)
        e[:3,3] = images[i].tvec; e[3,3] = 1; extrinsic[i] = e
    q = [(i,j) for i in range(n) for j in range(i+1,n)]
    print("算 %d 对评分..." % len(q), flush=True)
    p = mp.Pool(processes=12)
    res = p.map(partial(C.calc_score, images=images, points3d=points3d, args=A, extrinsic=extrinsic), q)
    p.close(); p.join()
    score = np.zeros((n,n))
    for i,j,s in res: score[i,j]=s; score[j,i]=s
    np.save(SC, score)

def rd(p):
    L = open(p).read().split('\n'); m = int(L[0]); o=[]
    for i in range(m):
        fl = L[2+2*i].split(); k=int(fl[0])
        o.append([int(fl[1+2*j]) for j in range(k)])
    return o
old = rd(REF)
NUM = min(20, n-1)                      # colmap2mvsnet_np2.py:418
merged, added = [], []
for i in range(n):
    keep = list(old[i])                  # 旧的一个不动, 顺序不动
    extra = [int(k) for k in np.argsort(score[i])[::-1] if int(k) not in keep and int(k) != i]
    add = extra[:NUM-len(keep)]
    added.append(len(add))
    merged.append(keep + add)

with open(OUT, "w") as f:
    f.write('%d\n' % n)
    for i, sv in enumerate(merged):
        f.write('%d\n%d ' % (i, len(sv)))
        for k in sv: f.write('%d %d ' % (k, int(score[i,k])))
        f.write('\n')

new = rd(OUT)
bad = [i for i in range(n) if new[i][:len(old[i])] != old[i]]
print("\n[判据 1] 前 %d 个逐字不变: %d / %d %s" % (len(old[0]), n-len(bad), n, "✅" if not bad else "🔴"))
print("[判据 2] 每 ref src 数: %s" % sorted(set(len(x) for x in new)))
print("[判据 3] 每 ref 无重复: %s" % ("✅" if all(len(set(x))==len(x) for x in new) else "🔴"))
print("[判据 4] 无自引用: %s" % ("✅" if all(i not in new[i] for i in range(n)) else "🔴"))
print("平均新增 %.1f 个 src" % (sum(added)/n))
