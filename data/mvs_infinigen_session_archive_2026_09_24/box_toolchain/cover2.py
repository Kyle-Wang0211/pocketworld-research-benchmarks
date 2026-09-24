# -*- coding: utf-8 -*-
"""任意臂的整圈覆盖率。用法: cover2.py tag=dir tag=dir ...
相机基准恒为 full_ep0(用户一直在看的那套), 36 个机位(18 个俯角 el=0.35 + 18 个掠射 el=0.05)。"""
import math, json, sys
args = sys.argv[1:]
sys.argv = ["x", "--mode", "stills", "--out", "/tmp/x"]
import orbit
V0 = json.load(open("/root/bins_full/meta.json"))["full_ep0"]
V = {"radius": V0["radius"]}
base = {"tx": V0["med"][0], "ty": V0["med"][1], "tz": V0["med"][2], "dist": V0["radius"]*2.4}
W, H = 1000, 750
arms = []
for a in args:
    t, d = a.split("=", 1)
    arms.append((t, orbit.Arm(t, d)))
acc = {t: [] for t, _ in arms}
for i in range(36):
    az = 0.6 + 2*math.pi*(i % 18)/18.0
    el = 0.35 if i < 18 else 0.05
    flat = orbit.mvp_matrix(dict(base, az=az, el=el), V, W, H)
    for t, a in arms:
        _, hit = a.render(flat, W, H)
        acc[t].append(100.0*hit/(W*H))
print()
print("%-16s %12s %10s %10s %10s" % ("臂", "点数", "覆盖均值", "最低", "最高"))
for t, a in arms:
    v = acc[t]
    print("%-16s %12s %9.2f%% %9.2f%% %9.2f%%" % (t, format(a.n, ","), sum(v)/len(v), min(v), max(v)))
