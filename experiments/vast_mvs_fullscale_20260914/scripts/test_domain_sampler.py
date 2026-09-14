# -*- coding: utf-8 -*-
"""EqualDomainSampler 验证 (用官方 MVSDataset 读真实 list, 不用自己复刻的解析):
  ① 每 epoch 每域被抽次数 == N (精确, 按构造应恰好相等)
  ② 大域: 两个 epoch 抽到的集合不同 (轮换);  小域(<N): 每条出现次数只取 floor/ceil 两个值
  ③ DataLoader 长度 = N*域数/batch  (OneCycleLR 总步数据此)
  ④ 阴性对照: 不用 sampler 时各域占比 = list 里的元组占比 (官方拼接)
"""
import os, sys, collections
sys.path.insert(0, "/root/diffmvs_full"); os.chdir("/root/diffmvs_full")
from torch.utils.data import DataLoader
from datasets.blend import MVSDataset
from datasets.domain_sampler import EqualDomainSampler, domain_of

LIST = sys.argv[1] if len(sys.argv) > 1 else "/root/diffmvs/lists/ab/train.txt"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
ds = MVSDataset("/root/monotrain", LIST, "train", 8, 384)
s = EqualDomainSampler(ds.metas, N, seed=0)
sizes = s.sizes()
print("域大小:", sizes)

seen = []
for ep in range(2):
    idx = list(iter(s))
    cnt = collections.Counter(domain_of(ds.metas[i][0]) for i in idx)
    per_item = collections.Counter(idx)
    print("epoch %d: 每域次数 %s  总 %d" % (ep, dict(cnt), len(idx)))
    for d in s.domains:
        assert cnt[d] == N, "① FAIL %s: %d != %d" % (d, cnt[d], N)
        reps = sorted({per_item[int(i)] for i in s.idx[d].tolist() if int(i) in per_item})
        if sizes[d] < N:
            exp = {N // sizes[d], -(-N // sizes[d])}
            assert set(reps) <= exp, "② FAIL 小域 %s 出现次数 %s 不在 %s" % (d, reps, exp)
        else:
            assert reps == [1], "② FAIL 大域 %s 有重复: %s" % (d, reps)
    seen.append({d: set(int(i) for i in idx if domain_of(ds.metas[i][0]) == d) for d in s.domains})
for d in s.domains:
    if sizes[d] >= N:
        ov = len(seen[0][d] & seen[1][d]) / float(N)
        print("  大域 %s 两 epoch 重叠 %.3f (随机期望 ~%.3f)" % (d, ov, N / float(sizes[d])))
        assert seen[0][d] != seen[1][d], "② FAIL 大域 %s 两 epoch 完全相同" % d
print("① ② PASS")

dl = DataLoader(ds, 4, sampler=EqualDomainSampler(ds.metas, N, 0), num_workers=0, drop_last=True)
assert len(dl) == N * len(s.domains) // 4, "③ FAIL len(dl)=%d" % len(dl)
print("③ PASS: len(DataLoader) =", len(dl), "= %d*%d/4" % (N, len(s.domains)))

tot = len(ds.metas)
print("④ 阴性对照(官方拼接, 不用 sampler)各域占比:",
      {d: "%.1f%%" % (100.0 * sizes[d] / tot) for d in s.domains},
      "| sampler 下每域 %.1f%%" % (100.0 / len(s.domains)))
