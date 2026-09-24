# -*- coding: utf-8 -*-
"""任意两臂的同机位轨迹视频。用法:
     orbit2.py --out DIR --frames N --pane "Label::tag::dir" --pane "Label::tag::dir"
相机/渲染全部复用 orbit.py(其相机数学逐字转写自 build_page_cli.py)。"""
import os, sys, math, json, time
sys.argv_keep = list(sys.argv)
import argparse
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--w", type=int, default=1400)
ap.add_argument("--h", type=int, default=1050)
ap.add_argument("--frames", type=int, default=180)
ap.add_argument("--pane", action="append", required=True)
a = ap.parse_args()
sys.argv = ["x", "--mode", "stills", "--out", "/tmp/x"]
import orbit
from PIL import Image

os.makedirs(a.out, exist_ok=True)
V0 = json.load(open("/root/bins_full/meta.json"))["full_ep0"]
V = {"radius": V0["radius"]}
base = {"tx": V0["med"][0], "ty": V0["med"][1], "tz": V0["med"][2], "dist": V0["radius"]*2.4}
print("相机基准 full_ep0: med=%s radius=%.3f" % ([round(x, 3) for x in V0["med"]], V0["radius"]), flush=True)

arms = []
for spec in a.pane:
    lab, tag, d = spec.split("::")
    arms.append((lab, orbit.Arm(tag, d)))

t0 = time.time(); n = a.frames
for i in range(n):
    if i < n//2:
        az, el = 0.6 + 2*math.pi*(i/(n//2)), 0.35
    else:
        az, el = 0.6 + 2*math.pi*((i-n//2)/(n-n//2)), 0.05
    flat = orbit.mvp_matrix(dict(base, az=az, el=el), V, a.w, a.h)
    tiles = []
    for lab, arm in arms:
        rgb, hit = arm.render(flat, a.w, a.h)
        tiles.append(orbit.label(Image.fromarray(rgb), lab,
                     "%s pts  |  %.1f%% of pixels covered" % (format(arm.n, ","), 100.0*hit/(a.w*a.h))))
    canvas = Image.new("RGB", (a.w*len(tiles)+4*(len(tiles)-1), a.h), (34, 34, 34))
    for k, t in enumerate(tiles):
        canvas.paste(t, (k*(a.w+4), 0))
    canvas.save(os.path.join(a.out, "f%05d.png" % i), compress_level=3)
    if i % 20 == 0:
        e = time.time()-t0
        print("  %3d/%d  已 %.0fs  预计 %.0fs" % (i, n, e, e/max(i, 1)*n), flush=True)
print("渲染完成 %.0fs" % (time.time()-t0), flush=True)
