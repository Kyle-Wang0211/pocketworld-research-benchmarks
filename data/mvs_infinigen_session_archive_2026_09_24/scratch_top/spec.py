# -*- coding: utf-8 -*-
"""Does a 768x576 JPEG actually carry 768-wide detail, or is it an interpolated blow-up of 640x480?
Alarm-capable criterion: horizontal power spectrum. An image resampled UP from 640 has (almost) no
energy above f = 640/768 = 0.833 x Nyquist. Score = mean power in [0.88,1.00]Nyq / mean power in
[0.55,0.75]Nyq.  POSITIVE CONTROL: take a known-native-768 image, 768->640->768 through the exact
code path the converters used (INTER_AREA + JPEG q95), and re-measure. If the score of that control
is NOT far below the untouched original, the whole test is meaningless and must be thrown away."""
import numpy as np, cv2, os, re, random, io
ROOT="/root/monotrain"; HEX24=re.compile(r"^[0-9a-f]{24}$")
RULES=[("sp_","sp_SimpleProc"),("ta_","ta_TartanAir"),("tg_","tg_TartanGround"),("gso_","gso_GSO"),("ak_","ak_ARKitScenes")]
def dom(s):
    for p,n in RULES:
        if s.startswith(p): return n
    return "hex_BlendedMVG" if HEX24.match(s) else None

def hscore(im):
    """im: float grayscale HxW"""
    H,W=im.shape
    x=im-im.mean(axis=1,keepdims=True)
    x=x*np.hanning(W)[None,:]
    P=(np.abs(np.fft.rfft(x,axis=1))**2).mean(axis=0)
    f=np.arange(P.size)/(W/2.0)           # 1.0 == Nyquist
    hi=P[(f>=0.88)&(f<=1.00)].mean()
    mid=P[(f>=0.55)&(f<=0.75)].mean()
    return float(hi/max(mid,1e-30)), P, f

b={}
for s in sorted(os.listdir(ROOT)):
    d=dom(s)
    if d: b.setdefault(d,[]).append(s)
r=random.Random(11)
print("cv2",cv2.__version__)
print("%-16s %-12s %-12s %-12s"%("domain","score","ctl 640rt","ratio(score/ctl)"))
print("-"*70)
res={}
for d in sorted(b):
    sc,ct=[],[]
    for s in r.sample(b[d],10):
        idir=os.path.join(ROOT,s,"blended_images"); fs=sorted(os.listdir(idir))
        for f in fs[:2]:
            g=cv2.imread(os.path.join(idir,f),cv2.IMREAD_GRAYSCALE)
            if g is None: continue
            gf=g.astype(np.float64)
            sc.append(hscore(gf)[0])
            # positive control: force it through 768->640->768 INTER_AREA + JPEG q95
            small=cv2.resize(g,(640,480),interpolation=cv2.INTER_AREA)
            up=cv2.resize(small,(768,576),interpolation=cv2.INTER_AREA)
            ok,buf=cv2.imencode(".jpg",up,[cv2.IMWRITE_JPEG_QUALITY,95])
            rt=cv2.imdecode(buf,cv2.IMREAD_GRAYSCALE).astype(np.float64)
            ct.append(hscore(rt)[0])
    a,c=float(np.median(sc)),float(np.median(ct))
    res[d]=(a,c)
    print("%-16s %-12.5f %-12.5f %-12.3f"%(d,a,c,a/max(c,1e-12)))
print()
print("Interpretation: a domain whose score sits at/below its own 640-roundtrip control")
print("carries no real 768-wide detail. A domain far above the control is genuinely 768 native.")
