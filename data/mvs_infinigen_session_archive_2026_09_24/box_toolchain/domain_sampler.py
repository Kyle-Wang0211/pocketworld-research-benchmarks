# -*- coding: utf-8 -*-
"""每 epoch 每个数据集等量采样 —— 整句复刻 DUSt3R §4 (arXiv 2312.14132):
    "During each epoch, we randomly sample an equal number of pairs from each dataset
     to equalize disparities in dataset sizes."

可选: UniMax 重复封顶 (Chung et al., ICLR 2023, arXiv 2304.09151 §3 "UniMax sampling"):
    按数据集大小升序分配预算; 对每个数据集, 若 均匀份额 > N × 大小 则只给 N × 大小 (N = 最大重复遍数),
    省下的预算由剩余更大的数据集均分。总预算不变 => len(DataLoader) 不变 => OneCycle 步数不变。
    repeat_cap = 0 时完全退化为 DUSt3R 等量采样。

官方 train.py:357 是 DataLoader(train_dataset, batch, shuffle=True) = 直接拼接(谁多谁占多)。
本文件只在 --domain_balance N > 0 时接入, N = 每个数据集每 epoch 抽的元组数 (等量档)。
  - 数据集 ≥ 份额: 不放回随机取 (下一 epoch 重新抽 => 大数据集逐 epoch 轮换)
  - 数据集 <  份额: 整轮打乱反复拼到份额 (同一 epoch 内每条样本出现次数相差 ≤ 1)
域 = scan 名前缀(显式表); 前缀不认识直接报错, 不允许静默归类。
"""
import re
import torch
from torch.utils.data import Sampler

_RULES = [("sp_scene_", "simpleproc"),
          ("ta_",       "tartanair"),
          ("tg_",       "tartanground"),
          ("gso_",      "gso"),
          ("ak_",       "arkitscenes")]
_HEX24 = re.compile(r"^[0-9a-f]{24}$")          # BlendedMVG 场景名 = 24 位十六进制


def domain_of(scan):
    for pre, name in _RULES:
        if scan.startswith(pre):
            return name
    if _HEX24.match(scan):
        return "blendedmvg"
    raise ValueError("unknown domain for scan %r" % scan)


def unimax_allocation(sizes, total_budget, repeat_cap):
    """UniMax §3: sizes={域:样本数}, total_budget=整个训练要抽的总样本数, repeat_cap=N(最大重复遍数)。
    返回 {域: 整个训练分到的样本数}。repeat_cap<=0 => 均分。"""
    names = sorted(sizes, key=lambda d: sizes[d])          # 升序
    alloc, B, k = {}, float(total_budget), len(names)
    for d in names:
        share = B / k
        cap = repeat_cap * sizes[d] if repeat_cap > 0 else float("inf")
        alloc[d] = min(share, cap)
        B -= alloc[d]
        k -= 1
    if B > 1e-6 * total_budget:      # 封顶后填不满预算: cap × 总独立样本 < 预算, UniMax 原文 "optimal N depends on the budget"
        raise ValueError("repeat_cap=%d 太小: 封顶容量 %.0f < 预算 %.0f, 最小可行 cap=%d"
                         % (repeat_cap, repeat_cap * sum(sizes.values()), total_budget,
                            -(-total_budget // sum(sizes.values()))))
    return alloc


class EqualDomainSampler(Sampler):
    def __init__(self, metas, per_domain, seed=0, repeat_cap=0, total_epochs=16):
        self.per_domain = int(per_domain)
        self.seed = int(seed)
        self.epoch = 0
        buckets = {}
        for i, m in enumerate(metas):            # metas[i] = (scan, ref_view, src_views)  blend.py:44
            buckets.setdefault(domain_of(m[0]), []).append(i)
        self.domains = sorted(buckets)
        self.idx = {d: torch.tensor(buckets[d], dtype=torch.long) for d in self.domains}
        sizes = self.sizes()
        budget_epoch = self.per_domain * len(self.domains)               # 每 epoch 总量, 封顶与否都不变
        alloc = unimax_allocation(sizes, budget_epoch * int(total_epochs), int(repeat_cap))
        # 整训分配 / epochs -> 每 epoch 各域条数 (取整后把余数补给最大的域, 保证总量精确)
        self.counts = {d: int(alloc[d] / int(total_epochs)) for d in self.domains}
        rest = budget_epoch - sum(self.counts.values())          # 取整余数 (< 域数) 补给未被封顶的最大域
        uncapped = [d for d in self.domains if repeat_cap <= 0 or alloc[d] < repeat_cap * sizes[d] - 1e-6]
        self.counts[max(uncapped or self.domains, key=lambda d: sizes[d])] += rest
        assert sum(self.counts.values()) == budget_epoch
        self.repeat_cap = int(repeat_cap)

    def sizes(self):
        return {d: int(len(self.idx[d])) for d in self.domains}

    def __len__(self):
        return sum(self.counts.values())

    def __iter__(self):
        g = torch.Generator()
        g.manual_seed(self.epoch + 777)   # DUSt3R easy_dataset.py ResizedDataset.set_epoch: default_rng(seed=epoch+777)
        self.epoch += 1
        parts = []
        for d in self.domains:
            pool, need, chosen = self.idx[d], self.counts[d], []
            while need > 0:
                perm = pool[torch.randperm(len(pool), generator=g)]
                take = perm[:need]
                chosen.append(take)
                need -= int(len(take))
            parts.append(torch.cat(chosen))
        allidx = torch.cat(parts)
        allidx = allidx[torch.randperm(len(allidx), generator=g)]
        return iter(allidx.tolist())
