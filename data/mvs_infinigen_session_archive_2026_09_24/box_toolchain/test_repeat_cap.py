# -*- coding: utf-8 -*-
"""UniMax 封顶验证 (真实全量 list, 官方 MVSDataset):
  ① cap=0 时每域恰 N (与旧行为逐位相同)
  ② cap=R 时: 总量仍 = N×域数 (len(DataLoader) 不变 => OneCycle 步数不变);
     被封顶的域整训条数 == R×size (差 ≤ epochs 的取整); 没被封顶的域份额相等 (差 ≤ 1)
  ③ 一个 epoch 真抽一遍, 各域次数 == counts
"""
import os, sys, collections
sys.path.insert(0, "/root/diffmvs_full"); os.chdir("/root/diffmvs_full")
from datasets.blend import MVSDataset
from datasets.domain_sampler import EqualDomainSampler, domain_of, unimax_allocation

N, E = 100000, 16
ds = MVSDataset("/root/monotrain", "lists/full/train.txt", "train", 8, 384)
s0 = EqualDomainSampler(ds.metas, N, 0, repeat_cap=0, total_epochs=E)
sizes = s0.sizes()
assert all(v == N for v in s0.counts.values()) and len(s0) == N * len(sizes), s0.counts
print("① cap=0: 每域 %d, 总 %d  PASS" % (N, len(s0)))
pass
rows = {}
import math
min_cap = math.ceil(N * len(sizes) * E / sum(sizes.values()))
for bad in (1, 4, min_cap - 1):
    try:
        EqualDomainSampler(ds.metas, N, 0, repeat_cap=bad, total_epochs=E); raise SystemExit('cap=%d 应当报错' % bad)
    except ValueError as e:
        print('  cap=%-2d 不可行, 正确拒绝: %s' % (bad, str(e)[:60]))
CAPS = (min_cap, 8, 10, 16)
for r in CAPS:
    s = EqualDomainSampler(ds.metas, N, 0, repeat_cap=r, total_epochs=E)
    assert len(s) == N * len(sizes), (r, len(s))
    alloc = unimax_allocation(sizes, N * len(sizes) * E, r)
    capped = [d for d in sizes if abs(alloc[d] - r * sizes[d]) < 1e-6]
    free = [d for d in sizes if d not in capped]
    for d in capped:
        assert abs(s.counts[d] * E - r * sizes[d]) <= E, (r, d, s.counts[d] * E, r * sizes[d])
    if free:
        vals = [s.counts[d] for d in free]
        assert max(vals) - min(vals) <= max(1, len(sizes)), (r, free, vals)   # 余数补给最大域, 允许小差
    rows[r] = s
    idx = list(iter(s))
    cnt = collections.Counter(domain_of(ds.metas[i][0]) for i in idx)
    assert dict(cnt) == s.counts, (r, dict(cnt), s.counts)
    print("  cap=%-2d ② PASS (封顶: %s)  ③ PASS 真抽一遍各域次数==counts" % (r, ",".join(capped) or "无"))
print("%-13s %8s | %s" % ("域", "size", " | ".join("cap=%-2d 每epoch(占比) 遍数" % r for r in CAPS)))
for d in sorted(sizes, key=lambda d: sizes[d]):
    cells = ["%7d(%4.1f%%) %5.1f遍" % (rows[r].counts[d], 100.0 * rows[r].counts[d] / (N * len(sizes)), rows[r].counts[d] * E / sizes[d]) for r in CAPS]
    print("%-13s %8d | %s" % (d, sizes[d], " | ".join(cells)))
print("对照 cap=0(现在在跑): 每域 %d (16.7%%), 整训遍数 = %s" % (N, {d: round(N * E / sizes[d], 1) for d in sizes}))
