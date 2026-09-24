# -*- coding: utf-8 -*-
"""每 epoch 每个数据集等量采样 —— 整句复刻 DUSt3R §4 (arXiv 2312.14132):
    "During each epoch, we randomly sample an equal number of pairs from each dataset
     to equalize disparities in dataset sizes."

官方 train.py:357 是 DataLoader(train_dataset, batch, shuffle=True) = 直接拼接(谁多谁占多)。
本文件只在 --domain_balance N > 0 时接入, N = 每个数据集每 epoch 抽的元组数。
  - 数据集 ≥ N: 不放回随机取 N (下一 epoch 重新抽 => 大数据集逐 epoch 轮换)
  - 数据集 <  N: 整轮打乱反复拼到 N (同一 epoch 内每条样本出现次数相差 ≤ 1)
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


class EqualDomainSampler(Sampler):
    def __init__(self, metas, per_domain, seed=0):
        self.per_domain = int(per_domain)
        self.seed = int(seed)
        self.epoch = 0
        buckets = {}
        for i, m in enumerate(metas):            # metas[i] = (scan, ref_view, src_views)  blend.py:44
            buckets.setdefault(domain_of(m[0]), []).append(i)
        self.domains = sorted(buckets)
        self.idx = {d: torch.tensor(buckets[d], dtype=torch.long) for d in self.domains}

    def sizes(self):
        return {d: int(len(self.idx[d])) for d in self.domains}

    def __len__(self):
        return self.per_domain * len(self.domains)

    def __iter__(self):
        g = torch.Generator()
        g.manual_seed(self.seed * 1000003 + self.epoch)   # 每 epoch 换一批
        self.epoch += 1
        parts = []
        for d in self.domains:
            pool, need, chosen = self.idx[d], self.per_domain, []
            while need > 0:
                perm = pool[torch.randperm(len(pool), generator=g)]
                take = perm[:need]
                chosen.append(take)
                need -= int(len(take))
            parts.append(torch.cat(chosen))
        allidx = torch.cat(parts)
        allidx = allidx[torch.randperm(len(allidx), generator=g)]
        return iter(allidx.tolist())
