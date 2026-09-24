# -*- coding: utf-8 -*-
"""thres=2 vs thres=3 同机位对照,正常点云原色。
相机数学 / 光栅化 / 标注 【整段复用 /root/orbit.py】, 不重写。

🔴 我自己定的只有视角选取: 两档俯视 el=0.35(页面默认) + 两档掠射 el=0.05
   —— 沿视线堆叠的多层被 z-buffer 挡住, 只有掠射角看得见分层。
"""
import os, sys, math, json, time
sys.path.insert(0, "/root")
import numpy as np, torch
from PIL import Image
import orbit
from orbit import Arm, mvp_matrix, label, DEV

W, H = 1600, 1200
OUT = "/root/gm_shots"
os.makedirs(OUT, exist_ok=True)

V0 = json.load(open("/root/bins_full/meta.json"))["full_ep0"]
V = {"radius": V0["radius"]}
base = {"tx": V0["med"][0], "ty": V0["med"][1], "tz": V0["med"][2], "dist": V0["radius"]*2.4}
print("相机基准 full_ep0: med=%s radius=%.3f" % ([round(x,3) for x in V0["med"]], V0["radius"]), flush=True)

# 先自证 t3 是不是 t2 的子集(只是文字结论, 不影响出图):
# filter.py:191 的 depth_est_averaged 对【全部】src 求均值, 与 thres 无关
# => thres 只决定保留哪些像素, 不改坐标 => 应有 t3 ⊂ t2。实测, 不假设。
# 🔴 torch CUDA 不支持 uint64 乘法(mul_cuda for UInt64) => 哈希放 numpy。
def h64(P):
    u = np.ascontiguousarray(P).view(np.uint32).reshape(-1, 3).astype(np.uint64)
    K = np.array([0x9E3779B97F4A7C15, 0xC2B2AE3D27D4EB4F, 0x165667B19E3779F9], dtype=np.uint64)
    return (u[:,0]*K[0]) ^ (u[:,1]*K[1]) ^ (u[:,2]*K[2])

p2 = np.fromfile("/root/bins_gm/GM_t2.pos", dtype="<f4").reshape(-1,3)
p3 = np.fromfile("/root/bins_gm/GM_t3.pos", dtype="<f4").reshape(-1,3)
t0 = time.time()
with np.errstate(over="ignore"):
    h2 = h64(p2); h3 = h64(p3)
s2 = np.sort(h2)
idx = np.searchsorted(s2, h3).clip(max=s2.size-1)
cover = int((s2[idx] == h3).sum())
print("[自证] t3 的 %s 点里 %s 个在 t2 中 (%.4f%%) ⇒ 收紧只做减法, 不移动点。用时 %.1fs"
      % (format(p3.shape[0],","), format(cover,","), 100.0*cover/p3.shape[0], time.time()-t0), flush=True)
del h2, h3, s2, idx, p2, p3

print("载入两臂(全量, 零抽稀):", flush=True)
A2 = Arm("GM_t2", "/root/bins_gm")
A3 = Arm("GM_t3", "/root/bins_gm")

COLS = [("thres = 2    现役生产档", A2, "%s 点" % format(A2.n, ",")),
        ("thres = 3    候选 (更紧)", A3, "%s 点   -%.1f%%" % (format(A3.n, ","), 100.0*(A2.n-A3.n)/A2.n))]

def shoot(az, el, tag):
    flat = mvp_matrix(dict(base, az=az, el=el), V, W, H)
    tiles = []
    for name, arm, sub in COLS:
        rgb, hit = arm.render(flat, W, H)
        tiles.append(label(Image.fromarray(rgb), name, "%s   |   覆盖 %.1f%% 像素" % (sub, 100.0*hit/(W*H))))
    cv = Image.new("RGB", (W*2+4, H), (34,34,34))
    cv.paste(tiles[0], (0,0)); cv.paste(tiles[1], (W+4,0))
    p = os.path.join(OUT, "%s.jpg" % tag)
    cv.convert("RGB").save(p, quality=92, subsampling=0)
    return p

for tag, az, el in [("v1_俯视", 0.6, 0.35), ("v2_掠射", 2.2, 0.05),
                    ("v3_俯视", 3.9, 0.35), ("v4_掠射", 5.2, 0.05)]:
    t = time.time(); p = shoot(az, el, tag)
    print("  %s  az=%.2f el=%.2f  %.1fs" % (p, az, el, time.time()-t), flush=True)
print("DONE", flush=True)
