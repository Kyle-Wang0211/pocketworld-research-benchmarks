# -*- coding: utf-8 -*-
"""必要条件测试 第二轮:换上对双峰敏感的不确定度。

第一轮结论: `conf0/1/2` 在低纹理区的预测力 <= 阴性对照(像素 x 坐标),且分箱不单调。
机制解释(agent 逐行核出): conf = `prob_volume_sum4` = 峰顶 +-2 平面的概率质量 =「众数多尖」,
**对双峰结构完全盲**。

本轮新增两列(都从 init stage 的真 softmax 概率体算,只读补丁,已过非确定性地板对照):
  · expvar  = sqrt(sum_d p(d)(d-E[d])^2) / (D-1)   <- UCSNet networks/ucsnet.py:62-63 (MIT)
              全二阶矩, 两峰相距 Delta 时 ~= (Delta/2)^2, 双峰必爆
  · secmass = 剔掉众数及其 +-2 邻域后剩下的概率质量  <- 更直接对口「双层」

判据(先声明后检验):
  低纹理区的 |Spearman| 必须【显著超过】阴性对照(像素 x 坐标, 上轮 -0.2594),且分箱单调。
  注意符号: conf 越大越确定 => 与分歧【负】相关; expvar/secmass 越大越不确定 => 【正】相关。
"""
import glob, os, sys
import numpy as np, cv2
sys.path.insert(0, "/root"); sys.path.insert(0, "/root/diffmvs")
from filter import reproject_with_depth, read_camera_parameters, read_pfm, read_pair_file
from layerruler import lowtex_mask

OUT = "/root/var_ep0"; PAIRF = "/root/pair20dir/pair.txt"
CAMIMG = "/root/mvs_P16k"; W, H, NREF = 16, 16, 16
W, H = 768, 576
pairs = read_pair_file(PAIRF)
step = max(1, len(pairs)//NREF); sample = pairs[::step][:NREF]

def fit(a, hw):
    if a.shape == hw: return a
    return cv2.resize(a.astype(np.float32), (hw[1], hw[0]), interpolation=cv2.INTER_NEAREST)

def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(np.float64); rb = np.argsort(np.argsort(b)).astype(np.float64)
    ra -= ra.mean(); rb -= rb.mean()
    d = np.sqrt((ra*ra).sum()*(rb*rb).sum())
    return float((ra*rb).sum()/d) if d > 0 else float("nan")

C0,C1,C2,EV,SM,DIFF,LOW,XC = [],[],[],[],[],[],[],[]
shape_note = None
for ref, srcs in sample:
    K,E,_,_ = read_camera_parameters(os.path.join(OUT,'cams/%08d_cam.txt'%ref))
    d0 = read_pfm(os.path.join(OUT,'depth_est/%08d.pfm'%ref))[0]
    hw = d0.shape
    c = [read_pfm(os.path.join(OUT,'conf%d/%08d.pfm'%(i,ref)))[0] for i in range(3)]
    ev = read_pfm(os.path.join(OUT,'expvar/%08d.pfm'%ref))[0]
    sm = read_pfm(os.path.join(OUT,'secmass/%08d.pfm'%ref))[0]
    if shape_note is None:
        shape_note = "depth %s | conf0 %s | expvar %s | secmass %s" % (hw, c[0].shape, ev.shape, sm.shape)
    lt = lowtex_mask(os.path.join(CAMIMG,"images","%08d.jpg"%ref), W, H).cpu().numpy().reshape(H,W).astype(bool)
    xg,yg = np.meshgrid(np.arange(hw[1]), np.arange(hw[0]))
    dd=[]
    for s in srcs:
        Ks,Es,_,_ = read_camera_parameters(os.path.join(OUT,'cams/%08d_cam.txt'%s))
        ds = read_pfm(os.path.join(OUT,'depth_est/%08d.pfm'%s))[0]
        dr,_,_,_,_ = reproject_with_depth(d0,K,E,ds,Ks,Es)
        dd.append(np.abs(dr-d0)/np.maximum(d0,1e-6))
    med = np.median(np.stack(dd),0)
    ok = (d0>0)&np.isfinite(med)
    sub = np.zeros_like(ok); sub[::4,::4]=True; ok &= sub
    C0.append(fit(c[0],hw)[ok]); C1.append(fit(c[1],hw)[ok]); C2.append(fit(c[2],hw)[ok])
    EV.append(fit(ev,hw)[ok]); SM.append(fit(sm,hw)[ok])
    DIFF.append(med[ok]); LOW.append(fit(lt.astype(np.float32),hw).astype(bool)[ok]); XC.append(xg[ok].astype(np.float64))
C0,C1,C2,EV,SM,DIFF,LOW,XC = map(np.concatenate,(C0,C1,C2,EV,SM,DIFF,LOW,XC))
print("尺寸: %s" % shape_note)
print("样本 %s (低纹理 %.1f%%)\n" % (format(len(DIFF),","), 100*LOW.mean()))

COLS = [("conf 三者最小(上轮)", np.minimum(np.minimum(C0,C1),C2), "负"),
        ("★ expvar (UCSNet 二阶矩)", EV, "正"),
        ("★ secmass (第二峰质量)", SM, "正"),
        ("🔴 像素 x 坐标(阴性对照)", XC, "—")]
for tag, m in (("全图", np.ones_like(LOW)), ("低纹理区 ← 判据在这", LOW)):
    print("【%s】n=%s" % (tag, format(int(m.sum()),",")))
    for n,v,sgn in COLS:
        r = spearman(v[m], DIFF[m])
        print("  %-26s Spearman %+8.4f   (|r|=%.4f, 期望符号 %s)" % (n, r, abs(r), sgn))
    print()

print("十分位分箱(看单调性; 分歧中位越低越好, 期望 expvar/secmass 越大分歧越大):")
for name, v in (("★ expvar", EV), ("★ secmass", SM)):
    for tag, m in (("全图", np.ones_like(LOW)), ("低纹理区", LOW)):
        vv, dd2 = v[m], DIFF[m]
        q = np.quantile(vv, np.linspace(0,1,11))
        row = []
        for i in range(10):
            sel = (vv>=q[i])&(vv<=q[i+1]) if i==9 else (vv>=q[i])&(vv<q[i+1])
            row.append(np.median(dd2[sel]) if sel.sum()>=100 else float("nan"))
        mono = all(row[i] <= row[i+1]*1.15 for i in range(9) if np.isfinite(row[i]) and np.isfinite(row[i+1]))
        print("  %-10s 【%s】 %s   %s" % (name, tag, " ".join("%.4f"%x for x in row),
                                          "✅单调" if mono else "🔴不单调"))
