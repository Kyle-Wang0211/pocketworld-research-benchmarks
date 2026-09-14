#!/usr/bin/env python3
"""把 DA3 官方导出的 scene.glb 转成查看页用的 .pos/.col,并与官方768 点云做 bbox 阳性对照。"""
import sys, numpy as np, trimesh, os, json
GLB, OUTDIR, TAG = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(OUTDIR, exist_ok=True)
s = trimesh.load(GLB, process=False)
pos=[]; col=[]
for name, g in (s.geometry.items() if hasattr(s,"geometry") else [("g",s)]):
    if not hasattr(g, "visual"): continue   # 跳过相机线框 Path3D
    v = np.asarray(g.vertices, dtype=np.float32)
    if v.size==0: continue
    c = None
    if getattr(g,"colors",None) is not None and len(g.colors): c=np.asarray(g.colors)[:,:3]
    elif getattr(g.visual,"vertex_colors",None) is not None and len(g.visual.vertex_colors): c=np.asarray(g.visual.vertex_colors)[:,:3]
    if c is None: c=np.full((len(v),3),200,np.uint8)
    pos.append(v); col.append(np.asarray(c,dtype=np.uint8))
    print(f"  {name}: {len(v):,}")
P=np.concatenate(pos); C=np.concatenate(col)
print(f"DA3 点数 {len(P):,}")
print("DA3   bbox min", np.round(P.min(0),3), "max", np.round(P.max(0),3))
R=np.fromfile("/root/bins_fc/fusecut.pos", dtype=np.float32).reshape(-1,3)
print("官方768 bbox min", np.round(R.min(0),3), "max", np.round(R.max(0),3), "(展示帧,y/z已取反)")
Rr = R*np.array([1,-1,-1],np.float32)
print("官方768 反回 COLMAP 帧 min", np.round(Rr.min(0),3), "max", np.round(Rr.max(0),3))
P.astype(np.float32).tofile(f"{OUTDIR}/{TAG}.pos")
C.astype(np.uint8).tofile(f"{OUTDIR}/{TAG}.col")
json.dump({TAG:{"n":int(len(P)),"med":np.median(P,0).tolist(),
                "radius":float(np.percentile(np.linalg.norm(P-np.median(P,0),axis=1),90))}},
          open(f"{OUTDIR}/meta_{TAG}.json","w"))
print("写出", OUTDIR, TAG)
