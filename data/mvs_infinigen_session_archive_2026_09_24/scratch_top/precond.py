# -*- coding: utf-8 -*-
"""必要条件测试: CasDiffMVS 的逐像素置信度, 到底能不能预测【跨视图深度分歧】?

为什么必须先测这个:
  「判据带宽随不确定度自适应」这条路的前提是【我们手上有一个能代表不确定度的量】。
  如果 conf 跟实际分歧不相关, 那后面所有机制都是空的, 这条线当场死, 省掉所有功夫。

口径:
  · 分歧 = 上游 filter.py 自己算的那两个量(逐字复用 reproject_with_depth, 不重写几何):
        dist                = 重投影像素偏移
        relative_depth_diff = |重投影深度 - 参考深度| / 参考深度
    每个 ref 像素对 20 个 src 各算一次, 取【中位数】作为该像素的分歧。
  · 相关性用 Spearman(秩相关), 对单调但非线性的关系稳健。
  · 🔴 阴性对照: 同时算 conf 与【像素 x 坐标】的相关。x 坐标与分歧【应当】无关,
    若它也出现强相关, 说明我的统计口径有问题, 本测试作废。
"""
import glob, os, sys
import numpy as np, cv2
sys.path.insert(0, "/root"); sys.path.insert(0, "/root/diffmvs")
from filter import reproject_with_depth, read_camera_parameters, read_pfm, read_pair_file
from layerruler import lowtex_mask

OUT = "/root/lg_ep0"; PAIRF = "/root/pair20dir/pair.txt"
CAMIMG = "/root/mvs_P16k"; W, H, NREF = 768, 576, 16
pairs = read_pair_file(PAIRF)
step = max(1, len(pairs)//NREF); sample = pairs[::step][:NREF]
print("ref %d 个, 每个 %d 个 src\n" % (len(sample), len(sample[0][1])), flush=True)

def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(np.float64)
    rb = np.argsort(np.argsort(b)).astype(np.float64)
    ra -= ra.mean(); rb -= rb.mean()
    d = np.sqrt((ra*ra).sum() * (rb*rb).sum())
    return float((ra*rb).sum()/d) if d > 0 else float("nan")

CONF, DIFF, DIST, LOW, XC = [], [], [], [], []
for ref, srcs in sample:
    K, E, _, _ = read_camera_parameters(os.path.join(OUT, 'cams/%08d_cam.txt' % ref))
    d0 = read_pfm(os.path.join(OUT, 'depth_est/%08d.pfm' % ref))[0]
    c = [read_pfm(os.path.join(OUT, 'conf%d/%08d.pfm' % (i, ref)))[0] for i in range(3)]
    lt = lowtex_mask(os.path.join(CAMIMG, "images", "%08d.jpg" % ref), W, H).cpu().numpy().reshape(H, W).astype(bool)
    xg, yg = np.meshgrid(np.arange(W), np.arange(H))
    dd, ds = [], []
    for s in srcs:
        Ks, Es, _, _ = read_camera_parameters(os.path.join(OUT, 'cams/%08d_cam.txt' % s))
        dsrc = read_pfm(os.path.join(OUT, 'depth_est/%08d.pfm' % s))[0]
        dr, x2, y2, _, _ = reproject_with_depth(d0, K, E, dsrc, Ks, Es)
        dd.append(np.abs(dr - d0) / np.maximum(d0, 1e-6))
        ds.append(np.sqrt((x2 - xg)**2 + (y2 - yg)**2))
    med_diff = np.median(np.stack(dd), 0); med_dist = np.median(np.stack(ds), 0)
    ok = (d0 > 0) & np.isfinite(med_diff) & np.isfinite(med_dist)
    sub = np.zeros_like(ok); sub[::4, ::4] = True; ok &= sub        # 抽稀, 16 万点/图够了
    CONF.append(np.stack([x[ok] for x in c], 1)); DIFF.append(med_diff[ok])
    DIST.append(med_dist[ok]); LOW.append(lt[ok]); XC.append(xg[ok].astype(np.float64))
CONF = np.concatenate(CONF); DIFF = np.concatenate(DIFF)
DIST = np.concatenate(DIST); LOW = np.concatenate(LOW); XC = np.concatenate(XC)
print("样本 %s 个 (低纹理 %.1f%%)\n" % (format(len(DIFF), ","), 100*LOW.mean()))

NAMES = ["conf0", "conf1", "conf2", "conf 三者最小", "conf 三者乘积"]
COLS = [CONF[:,0], CONF[:,1], CONF[:,2], CONF.min(1), CONF.prod(1)]
for tag, m in (("全图", np.ones_like(LOW)), ("低纹理区", LOW)):
    print("【%s】n=%s" % (tag, format(int(m.sum()), ",")))
    print("  %-14s  %22s  %22s" % ("不确定度候选", "vs 相对深度分歧", "vs 重投影像素偏移"))
    for n, v in zip(NAMES, COLS):
        print("  %-14s  Spearman %9.4f        %9.4f" % (n, spearman(v[m], DIFF[m]), spearman(v[m], DIST[m])))
    print("  %-14s  Spearman %9.4f        %9.4f   <- 🔴阴性对照(应≈0)"
          % ("像素 x 坐标", spearman(XC[m], DIFF[m]), spearman(XC[m], DIST[m])))
    print()

# 分箱看单调性 —— 相关系数会被长尾骗, 分箱不会
print("按 conf(三者最小) 十分位分箱, 看相对深度分歧的中位数是否单调:")
for tag, m in (("全图", np.ones_like(LOW)), ("低纹理区", LOW)):
    v = CONF.min(1)[m]; d = DIFF[m]
    q = np.quantile(v, np.linspace(0, 1, 11))
    print("  【%s】" % tag)
    for i in range(10):
        sel = (v >= q[i]) & (v <= q[i+1]) if i == 9 else (v >= q[i]) & (v < q[i+1])
        if sel.sum() < 100: continue
        print("    第%2d档 conf[%.4f,%.4f]  n=%8d  分歧中位 %.5f  >1%%占比 %5.1f%%"
              % (i+1, q[i], q[i+1], sel.sum(), np.median(d[sel]), 100*np.mean(d[sel] > 0.01)))
