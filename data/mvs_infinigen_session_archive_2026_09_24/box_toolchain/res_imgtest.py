# -*- coding: utf-8 -*-
import numpy as np, cv2, os, re, random, json
print("cv2", cv2.__version__)
# 1) What does INTER_AREA do when UPscaling 640->768 ?
rng=np.random.default_rng(0)
a=rng.integers(0,255,(480,640,3)).astype(np.uint8)
area=cv2.resize(a,(768,576),interpolation=cv2.INTER_AREA)
near=cv2.resize(a,(768,576),interpolation=cv2.INTER_NEAREST)
lin =cv2.resize(a,(768,576),interpolation=cv2.INTER_LINEAR)
print("INTER_AREA upscale == INTER_NEAREST ? ", np.array_equal(area,near),
      " == INTER_LINEAR ?", np.array_equal(area,lin),
      " maxdiff(area,near)=",int(np.abs(area.astype(int)-near.astype(int)).max()))
# 2) grid-alignment on real JPEGs: within-group vs across-group adjacent-column abs diff
ROOT="/root/monotrain"; HEX24=re.compile(r"^[0-9a-f]{24}$")
RULES=[("sp_","sp_SimpleProc"),("ta_","ta_TartanAir"),("tg_","tg_TartanGround"),("gso_","gso_GSO"),("ak_","ak_ARKitScenes")]
def dom(s):
    for p,n in RULES:
        if s.startswith(p): return n
    return "hex_BlendedMVG" if HEX24.match(s) else None
b={}
for s in sorted(os.listdir(ROOT)):
    d=dom(s)
    if d: b.setdefault(d,[]).append(s)
r=random.Random(3)
print()
print("%-16s %-28s %-28s %s"%("domain","w0=640 within/across","w0=768(control)","verdict"))
for d in sorted(b):
    wi_all,ac_all=[],[]
    for s in r.sample(b[d],8):
        idir=os.path.join(ROOT,s,"blended_images"); fs=sorted(os.listdir(idir))
        for f in fs[:2]:
            im=cv2.imread(os.path.join(idir,f),cv2.IMREAD_GRAYSCALE).astype(np.int32)
            H,W=im.shape
            g=(np.arange(W)*640)//W
            m=g[1:]==g[:-1]
            dif=np.abs(im[:,1:]-im[:,:-1])
            wi=float(dif[:,m].mean()); ac=float(dif[:,~m].mean())
            wi_all.append(wi); ac_all.append(ac)
    wi=np.mean(wi_all); ac=np.mean(ac_all)
    v="*** NN-UPSCALED from 640 ***" if wi < 0.35*ac else "native 768 (no 640 grid)"
    print("%-16s within=%6.3f across=%6.3f ratio=%.3f   %s"%(d,wi,ac,wi/max(ac,1e-9),v))
