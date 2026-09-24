# -*- coding: utf-8 -*-
"""开训前的数据通路冒烟: 用官方 MVSDataset.__getitem__ 每个域真读 K 条元组 (图+深度+cam+mask),
检查形状/数值/掩码覆盖率; 再用 EqualDomainSampler(N=100000) 走一次 DataLoader 前 B 个 batch。
不建模型、不训练。"""
import os, sys, time, collections, numpy as np, torch
sys.path.insert(0, "/root/diffmvs_full"); os.chdir("/root/diffmvs_full")
from torch.utils.data import DataLoader
from datasets.blend import MVSDataset
from datasets.domain_sampler import EqualDomainSampler, domain_of

K = int(sys.argv[1]) if len(sys.argv) > 1 else 20
B = int(sys.argv[2]) if len(sys.argv) > 2 else 30
LISTS = os.environ.get("LISTS", "full")
ds = MVSDataset("/root/monotrain", "lists/%s/train.txt" % LISTS, "train", 8, 384)
by = collections.defaultdict(list)
for i, m in enumerate(ds.metas):
    by[domain_of(m[0])].append(i)
rng = np.random.RandomState(0)
print("%-13s %6s %14s %10s %10s %10s %s" % ("域", "n", "imgs.shape", "深度范围m", "mask覆盖", "ms/样本", "问题"))
for d in sorted(by):
    idx = rng.choice(by[d], K, replace=False)
    t0 = time.time(); cov = []; dmin = 1e9; dmax = 0; shp = None; bad = []
    for i in idx:
        s = ds[int(i)]
        imgs = s["imgs"]; imgs = np.stack(imgs) if isinstance(imgs, list) else np.asarray(imgs)   # blend.py 返回的是 list-of-views
        dep = np.asarray(s["depth"]["stage3"]); msk = np.asarray(s["mask"]["stage3"])
        shp = tuple(imgs.shape)
        if not np.isfinite(imgs).all(): bad.append("img nan")
        if not np.isfinite(dep).all(): bad.append("depth nan")
        v = dep[msk > 0]
        if v.size: dmin = min(dmin, float(v.min())); dmax = max(dmax, float(v.max()))
        cov.append(float((msk > 0).mean()))
        dv = s["depth_values"]
        if not (np.isfinite(dv).all() and dv[0] > 0): bad.append("depth_values")
    print("%-13s %6d %14s %4.2f–%-5.1f %9.1f%% %10.0f %s" % (d, len(by[d]), shp, dmin, dmax, 100 * np.mean(cov),
          (time.time() - t0) / K * 1000, ",".join(sorted(set(bad))) or "-"))

s = EqualDomainSampler(ds.metas, 100000, 0)
dl = DataLoader(ds, 4, sampler=s, num_workers=8, drop_last=True)
print("DataLoader len =", len(dl), "(= 100000*%d/4)" % len(s.domains))
t0 = time.time(); cnt = collections.Counter()
for bi, batch in enumerate(dl):
    im = batch["imgs"]   # 官方 collate: list of 8 views, 每个 (4,3,H,W)
    assert (len(im) == 8 and tuple(im[0].shape) == (4, 3, 576, 768)) if isinstance(im, list) else tuple(im.shape)[:2] == (4, 8), type(im)
    if bi + 1 >= B: break
print("前 %d 个 batch OK, %.2f s/batch (8 workers, 不含 GPU)" % (B, (time.time() - t0) / B))
