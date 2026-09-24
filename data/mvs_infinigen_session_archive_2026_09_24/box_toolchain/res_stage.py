import numpy as np, cv2, os, re, random
def read_pfm(path):
    with open(path,"rb") as f:
        t=f.readline().rstrip(); color=(t==b"PF"); dims=f.readline()
        while dims.strip().startswith(b"#"): dims=f.readline()
        w,h=map(int,dims.split()); sc=float(f.readline().rstrip())
        e="<" if sc<0 else ">"
        a=np.frombuffer(f.read(w*h*(3 if color else 1)*4),dtype=e+"f").reshape((h,w))
        return np.flipud(a).copy()
ROOT="/root/monotrain"; HEX=re.compile(r"^[0-9a-f]{24}$")
R=[("sp_","sp_SimpleProc"),("ta_","ta_TartanAir"),("tg_","tg_TartanGround"),("gso_","gso_GSO"),("ak_","ak_ARKitScenes")]
def dom(s):
    for p,n in R:
        if s.startswith(p): return n
    return "hex_BlendedMVG" if HEX.match(s) else None
b={}
for s in sorted(os.listdir(ROOT)):
    d=dom(s)
    if d: b.setdefault(d,[]).append(s)
rng=random.Random(2)
print("distinct depth values present at each supervision stage (blend.py:126-134), median over 8 scenes, as %% of that stage pixel count")
print("%-16s %-20s %-20s %-20s %-20s"%("domain","stage1 96x72","stage2 192x144","stage3 384x288","stage4 768x576"))
for d in sorted(b):
    acc={1:[],2:[],3:[],4:[]}
    for s in rng.sample(b[d],8):
        dd=os.path.join(ROOT,s,"rendered_depth_maps"); fs=sorted(os.listdir(dd))
        a=read_pfm(os.path.join(dd,fs[0])); h,w=a.shape
        ms={1:cv2.resize(a,(w//8,h//8),interpolation=cv2.INTER_NEAREST),
            2:cv2.resize(a,(w//4,h//4),interpolation=cv2.INTER_NEAREST),
            3:cv2.resize(a,(w//2,h//2),interpolation=cv2.INTER_NEAREST),4:a}
        for k,v in ms.items(): acc[k].append(np.unique(v).size)
    row=[int(np.median(acc[k])) for k in (1,2,3,4)]
    npx=[96*72,192*144,384*288,768*576]
    print("%-16s"%d + "".join("%-20s"%("%d (%.0f%%)"%(r,100.0*r/n)) for r,n in zip(row,npx)))
