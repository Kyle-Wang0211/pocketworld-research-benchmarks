# -*- coding: utf-8 -*-
"""为什么 skyfix 之后多层更重 —— 直接量,不猜。

假设: 天空监督原本在教网络「大面积无纹理 => 输出最远档」, 是个无纹理区正则;
      去掉后白墙上网络失去默认答案, 预测发散 => 多层。
若成立, 应当看到: 新 ep0 在【低纹理像素】上
   (a) 置信度更高(错的也自信 => 过光度闸 => 变成层), 或
   (b) 深度预测更发散。
低纹理口径与 layerruler 完全相同(11x11 灰度 std 最平 25%)。
"""
import glob, os, sys
import numpy as np, torch, cv2
sys.path.insert(0, "/root")
from layerruler import lowtex_mask, read_cam
sys.path.insert(0, "/root/diffmvs")
from filter import read_pfm

W, H, N = 768, 576, 24
CAM = "/root/mvs_P16k"
ARMS = [("老 ep0", "/root/lg_ep0"), ("新 ep0 skyfix", "/root/sky_ep0")]
PHOTO = [0.3, 0.5, 0.5]

camfs = sorted(glob.glob(os.path.join(CAM, "cams", "*_cam.txt")))
step = max(1, len(camfs)//N); sel = camfs[::step][:N]
vids = [int(os.path.basename(p).split("_")[0]) for p in sel]
LT = {}
for p, v in zip(sel, vids):
    ip = os.path.join(CAM, "images", "%08d.jpg" % v)
    LT[v] = lowtex_mask(ip, W, H).cpu().numpy().astype(bool).reshape(H, W)
print("各图尺寸: conf0/1/2/depth 见下\n视图 %d 个, 低纹理像素占比 %.1f%%\n" % (len(vids), 100*np.mean([m.mean() for m in LT.values()])), flush=True)

hdr = "%-16s | %-22s | %-22s" % ("臂", "低纹理区", "高纹理区(对照)")
print(hdr); print("-"*len(hdr))
for lab, d in ARMS:
    acc = {k: [[], []] for k in ("c0","c1","c2","photo","dstd","dmed")}
    for v in vids:
        lt = LT[v]
        c0 = read_pfm(os.path.join(d,"conf0/%08d.pfm"%v))[0]
        c1 = read_pfm(os.path.join(d,"conf1/%08d.pfm"%v))[0]
        c2 = read_pfm(os.path.join(d,"conf2/%08d.pfm"%v))[0]
        dp = read_pfm(os.path.join(d,"depth_est/%08d.pfm"%v))[0]
        # 🔴 各级 conf 分辨率不同(stage 下采样), mask 要按各自尺寸重采
        def fit(a, ref):
            if a.shape == ref.shape: return a
            return cv2.resize(a.astype(np.uint8), (ref.shape[1], ref.shape[0]),
                              interpolation=cv2.INTER_NEAREST).astype(bool)
        ph = (c0>PHOTO[0]) & (fit(c1>PHOTO[1], c0) if c1.shape!=c0.shape else (c1>PHOTO[1])) \
             & (fit(c2>PHOTO[2], c0) if c2.shape!=c0.shape else (c2>PHOTO[2]))
        for i, base in enumerate((lt, ~lt)):
            acc["c0"][i].append(float(c0[fit(base,c0)].mean()))
            acc["c1"][i].append(float(c1[fit(base,c1)].mean()))
            acc["c2"][i].append(float(c2[fit(base,c2)].mean()))
            acc["photo"][i].append(float(ph[fit(base,ph)].mean()))
            m = fit(base, dp)
            dv = dp[m & (dp>0)]
            if dv.size: acc["dstd"][i].append(float(dv.std())); acc["dmed"][i].append(float(np.median(dv)))
    f = lambda k,i: np.mean(acc[k][i])
    print("%-16s | conf0 %.4f conf1 %.4f | conf0 %.4f conf1 %.4f" % (lab, f("c0",0), f("c1",0), f("c0",1), f("c1",1)))
    print("%-16s | conf2 %.4f 过闸 %.1f%% | conf2 %.4f 过闸 %.1f%%" % ("", f("c2",0), 100*f("photo",0), f("c2",1), 100*f("photo",1)))
    print("%-16s | 深度中位 %.3f m std %.3f | 深度中位 %.3f m std %.3f" % ("", f("dmed",0), f("dstd",0), f("dmed",1), f("dstd",1)))
    print("-"*len(hdr))
