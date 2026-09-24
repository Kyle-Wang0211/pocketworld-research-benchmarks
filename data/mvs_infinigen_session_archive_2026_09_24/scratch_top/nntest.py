# -*- coding: utf-8 -*-
"""Decide, per domain, the native grid a 768x576 depth map was nearest-neighbour upsampled FROM.
Criterion that can FAIL: for candidate native width w0, group output columns j by g(j)=floor(j*w0/W).
If the map really is an NN upsample from w0, EVERY pair of adjacent columns inside a group is byte-identical
=> score == 1.0000. A genuinely native map scores ~= the flat-content baseline (dup_col), far below 1.
Same for rows. Both must be 1.0 for the candidate to be accepted."""
import os, re, sys, random, json
import numpy as np

ROOT="/root/monotrain"
HEX24=re.compile(r"^[0-9a-f]{24}$")
RULES=[("sp_","sp_SimpleProc"),("ta_","ta_TartanAir"),("tg_","tg_TartanGround"),
       ("gso_","gso_GSO"),("ak_","ak_ARKitScenes")]
def dom(s):
    for p,n in RULES:
        if s.startswith(p): return n
    return "hex_BlendedMVG" if HEX24.match(s) else None

def read_pfm(path):
    with open(path,"rb") as f:
        t=f.readline().rstrip(); color=(t==b"PF")
        dims=f.readline()
        while dims.strip().startswith(b"#"): dims=f.readline()
        w,h=map(int,dims.split()); scale=float(f.readline().rstrip())
        end="<" if scale<0 else ">"
        a=np.frombuffer(f.read(w*h*(3 if color else 1)*4),dtype=end+"f")
        a=a.reshape((h,w,3) if color else (h,w))
        return np.flipud(a).copy()

def grid_score(a,h0,w0):
    H,W=a.shape
    gj=(np.arange(W)*w0)//W
    gi=(np.arange(H)*h0)//H
    mj=gj[1:]==gj[:-1]
    mi=gi[1:]==gi[:-1]
    if mj.sum()==0 or mi.sum()==0: return None
    eqc=(a[:,1:]==a[:,:-1])[:,mj]
    eqr=(a[1:,:]==a[:-1,:])[mi,:]
    return float(eqc.mean()), float(eqr.mean()), int(mj.sum()), int(mi.sum())

CANDS=[(576,768),(540,720),(480,640),(432,576),(384,512),(288,384),(240,320),(192,256),(144,192)]
scans=sorted(os.listdir(ROOT))
b={}
for s in scans:
    d=dom(s)
    if d: b.setdefault(d,[]).append(s)
rng=random.Random(7)
res={}
for d in sorted(b):
    rows=[]
    for s in rng.sample(b[d],min(10,len(b[d]))):
        dd=os.path.join(ROOT,s,"rendered_depth_maps")
        fs=sorted(os.listdir(dd))
        for f in fs[:1]:
            a=read_pfm(os.path.join(dd,f))
            H,W=a.shape
            base_c=float((a[:,1:]==a[:,:-1]).mean()); base_r=float((a[1:,:]==a[:-1,:]).mean())
            r={"scan":s,"base_dup_col":round(base_c,4),"base_dup_row":round(base_r,4),"cand":{}}
            for (h0,w0) in CANDS:
                if h0>H or w0>W: continue
                g=grid_score(a,h0,w0)
                if g is None: continue
                r["cand"]["%dx%d"%(w0,h0)]=[round(g[0],6),round(g[1],6)]
            rows.append(r)
    res[d]=rows
# report: for each domain, per candidate, min over scenes of min(col,row) score
print("%-16s %-10s %s"%("domain","baselineCR","candidate -> worst-case exact-NN score (col,row) across 10 scenes"))
for d,rows in res.items():
    bc=np.median([r["base_dup_col"] for r in rows]); br=np.median([r["base_dup_row"] for r in rows])
    print("="*100)
    print("%-16s base dup col=%.4f row=%.4f  (n=%d scenes)"%(d,bc,br,len(rows)))
    cands=list(rows[0]["cand"].keys())
    for c in cands:
        cs=[r["cand"][c][0] for r in rows if c in r["cand"]]
        rs=[r["cand"][c][1] for r in rows if c in r["cand"]]
        verdict="*** EXACT NN UPSAMPLE ***" if min(cs)>=0.999999 and min(rs)>=0.999999 else ""
        print("   %-10s col min %.6f mean %.6f | row min %.6f mean %.6f  %s"%(c,min(cs),np.mean(cs),min(rs),np.mean(rs),verdict))
