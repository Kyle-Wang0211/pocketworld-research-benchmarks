# -*- coding: utf-8 -*-
"""为判决页生成 bin/meta.json。算法逐字复刻 verdict_page/export_bins.py:41-50:
     center/ext = 1%/99% 分位(不用 min/max, 一颗飞点就能撑大包围盒)
     med = 全量中位数 ; radius = 到中位数距离的 p95
   并自带 build_page_cli.py::_check_frames 的两项预检:
     ① 文件字节数 == n*12   ② 采样中位数(step=997) 与 med 差 <= 0.25
   —— 先在远端拒绝, 免得拉 2.4 GB 到本地才发现建不了页。"""
import os, sys, json, struct
import numpy as np
D = sys.argv[1]; tags = sys.argv[2:]
meta = {}
for w in tags:
    p = os.path.join(D, w + ".pos")
    n = os.path.getsize(p) // 12
    pos = np.memmap(p, dtype="<f4", mode="r", shape=(n, 3))
    lo = np.percentile(pos, 1, axis=0); hi = np.percentile(pos, 99, axis=0)
    med = np.median(pos, 0)
    rad = float(np.percentile(np.linalg.norm(np.asarray(pos) - med, axis=1), 95))
    meta[w] = {"n": int(n), "center": ((lo + hi) / 2).tolist(),
               "ext": (hi - lo).tolist(), "med": med.astype(float).tolist(), "radius": rad}
    # ---- 预检①: 字节数
    assert os.path.getsize(p) == n * 12, "%s 字节数不是 12 的整数倍" % w
    # ---- 预检②: 复刻 _sampled_median(step=997)
    xs=[];ys=[];zs=[]
    with open(p,"rb") as f:
        for i in range(0, n, 997):
            f.seek(i*12); x,y,z = struct.unpack("<3f", f.read(12))
            xs.append(x); ys.append(y); zs.append(z)
    samp = [float(np.median(a)) for a in (xs,ys,zs)]
    dmax = max(abs(a-b) for a,b in zip(samp, meta[w]["med"]))
    ok = dmax <= 0.25
    print("%-12s n=%-11d med=%s  radius=%.3f" % (w, n, np.round(med,3).tolist(), rad))
    print("   预检: 采样中位数 %s  与 med 最大差 %.4f  (闸 0.25)  %s"
          % (np.round(samp,3).tolist(), dmax, "OK" if ok else "*** FAIL ***"))
    assert ok, "%s 采样中位数与 med 不符, 建页会被 _check_frames 拒绝" % w
    # ---- 预检③: 展示帧一致性(y,z 应为负 —— ply2bins 已翻过)
    print("   帧: med=[%.2f, %.2f, %.2f]  y/z 为负 => 展示帧 %s"
          % (med[0], med[1], med[2], "OK" if (med[1]<0 and med[2]<0) else "*** 可疑 ***"))
json.dump(meta, open(os.path.join(D, "meta.json"), "w"), ensure_ascii=False, indent=1)
print()
print("写出 %s/meta.json  (%d 臂)" % (D, len(meta)))
