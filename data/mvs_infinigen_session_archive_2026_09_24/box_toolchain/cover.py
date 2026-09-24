# -*- coding: utf-8 -*-
"""整圈覆盖率: 同一机位下, 每臂点云盖住多少像素。
量的是【面】不是【点】—— 点数多不等于覆盖广, 这正是高分辨率臂的争议点。"""
import math, json, sys
sys.argv=["x","--mode","stills","--out","/tmp/x"]
import orbit
V0=json.load(open("/root/bins_full/meta.json"))["full_ep0"]
V={"radius":V0["radius"]}
base={"tx":V0["med"][0],"ty":V0["med"][1],"tz":V0["med"][2],"dist":V0["radius"]*2.4}
W,H=1000,750
arms=[("768x576",orbit.Arm("full_ep0","/root/bins_full")),
      ("12MP",  orbit.Arm("ep0_12mp","/root/bins_12mp"))]
acc={k:[] for k,_ in arms}
N=36
for i in range(N):
    az=0.6+2*math.pi*(i%18)/18.0; el=0.35 if i<18 else 0.05
    flat=orbit.mvp_matrix(dict(base,az=az,el=el),V,W,H)
    for k,a in arms:
        _,hit=a.render(flat,W,H); acc[k].append(100.0*hit/(W*H))
print()
print("%-10s %10s %10s %10s" % ("臂","覆盖均值","最低","最高"))
for k,_ in arms:
    v=acc[k]; print("%-10s %9.2f%% %9.2f%% %9.2f%%" % (k,sum(v)/len(v),min(v),max(v)))
r=[b/a for a,b in zip(acc["768x576"],acc["12MP"])]
print()
print("12MP / 768 覆盖比: 均值 %.3f  (36 个机位全部 <1: %s)" % (sum(r)/len(r), all(x<1 for x in r)))
