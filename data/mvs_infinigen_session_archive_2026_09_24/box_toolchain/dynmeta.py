# -*- coding: utf-8 -*-
"""从 .pos bin 直接算页面 meta(与既有页同字段: n/center/ext/med/radius)。"""
import json, numpy as np, os
B = "/root/bins_dyn"
out = {}
for tag in ("dyn_base", "dyn_temple", "dyn_museum", "dyn_light"):
    p = os.path.join(B, tag + ".pos")
    a = np.fromfile(p, dtype=np.float32).reshape(-1, 3)
    lo, hi = a.min(0), a.max(0)
    med = np.median(a[::max(1, len(a) // 2000000)], axis=0)
    ext = (hi - lo)
    out[tag] = {"n": int(len(a)),
                "center": [float(x) for x in (lo + hi) / 2],
                "ext": [float(x) for x in ext],
                "med": [float(x) for x in med],
                "radius": float(np.linalg.norm(ext) / 2 * 0.5)}
    print("%-12s n=%-12d med=%s radius=%.3f" % (tag, out[tag]["n"],
          [round(float(x), 3) for x in med], out[tag]["radius"]))
json.dump(out, open(os.path.join(B, "meta.json"), "w"))
print("写出", os.path.join(B, "meta.json"))
