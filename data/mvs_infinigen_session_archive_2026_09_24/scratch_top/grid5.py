# -*- coding: utf-8 -*-
"""取舍前沿上的 5 档, 同机位网格对照(3 上 2 下)。相机/光栅化复用 /root/orbit.py。
被支配的两档([4,8,1600] 覆盖更低且多层更差、[6,8,1600] 同理)已剔除。"""
import os, sys, json, time
sys.path.insert(0, "/root")
import numpy as np, torch
from PIL import Image
import orbit
from orbit import Arm, mvp_matrix, label

W, H = 1150, 880
OUT = "/root/grid_shots"; os.makedirs(OUT, exist_ok=True)
V0 = json.load(open("/root/bins_full/meta.json"))["full_ep0"]
V = {"radius": V0["radius"]}
base = {"tx": V0["med"][0], "ty": V0["med"][1], "tz": V0["med"][2], "dist": V0["radius"]*2.4}

SPEC = [("现役  固定 thres=2",      "GM_t2",        "覆盖 91.93%  |  多层 61.99%"),
        ("自适应 [2,4,1300] 室内档", "GM20_dyn",     "覆盖 88.39%  |  多层 48.75%"),
        ("自适应 [3,4,1300]",       "DY_Panther",   "覆盖 83.10%  |  多层 42.39%"),
        ("自适应 [3,4,1600]",       "DY_Train",     "覆盖 80.99%  |  多层 37.72%"),
        ("自适应 [9,8,1600] 最狠",   "DY_Francis",   "覆盖 53.96%  |  多层 16.02%")]
arms = [(n, Arm(t, "/root/bins_gm"), s) for n, t, s in SPEC]

def shoot(az, el, tag):
    flat = mvp_matrix(dict(base, az=az, el=el), V, W, H)
    tiles = []
    for n, a, s in arms:
        rgb, hit = a.render(flat, W, H)
        tiles.append(label(Image.fromarray(rgb), n, "%s  |  %s 点" % (s, format(a.n, ","))))
    cv = Image.new("RGB", (W*3+8, H*2+4), (28, 28, 28))
    for i, t in enumerate(tiles):
        cv.paste(t, ((i % 3)*(W+4), (i//3)*(H+4)))
    p = os.path.join(OUT, "%s.jpg" % tag)
    cv.save(p, quality=90, subsampling=0)
    return p

for tag, az, el in [("g1_graze", 2.2, 0.05), ("g2_graze", 5.2, 0.05),
                    ("g3_top", 0.6, 0.35), ("g4_top", 3.9, 0.35)]:
    t = time.time(); p = shoot(az, el, tag)
    print("  %s  %.1fs" % (p, time.time()-t), flush=True)
print("DONE", flush=True)
