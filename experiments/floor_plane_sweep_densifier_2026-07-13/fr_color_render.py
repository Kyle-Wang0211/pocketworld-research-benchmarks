#!/usr/bin/env python3
"""Colorize LoFTR floor-rescue points with PRODUCTION-faithful sampling
(colorize_pipeline.dart :135-168 verbatim: px*scale-0.5, bilinear, avg over obs, round),
then top-down true-color floor render (SIFT vs SIFT+rescue). Pure numpy+PIL."""
import json, numpy as np, cv2
from collections import defaultdict
from PIL import Image
import fr_common as fc

FR = fc.FR
M = np.load(FR + "/fr_matches.npz")
pairs = sorted({k[:-3] for k in M.files if k.endswith("_p0")}, key=lambda s: tuple(map(int, s.split("_"))))
allmax = max(float(M[f"{p}_p0"][:,0].max()) for p in pairs if len(M[f"{p}_p0"]))
sx, sy = (fc.WORK_W/fc.MATCH_W, fc.WORK_H/fc.MATCH_H) if allmax <= fc.MATCH_W+2 else (1.0,1.0)
RM = cv2.USAC_MAGSAC if hasattr(cv2,"USAC_MAGSAC") else cv2.FM_RANSAC

# --- rebuild tracks (same as fr_triangulate) keeping observations ---
parent={}
def find(x):
    parent.setdefault(x,x); r=x
    while parent[r]!=r: r=parent[r]
    while parent[x]!=r: parent[x],x=r,parent[x]
    return r
def union(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: parent[rb]=ra
node_px=defaultdict(list); G=fc.GRID
for p in pairs:
    i,j=map(int,p.split("_"))
    p0=M[f"{p}_p0"].astype(np.float64)*[sx,sy]; p1=M[f"{p}_p1"].astype(np.float64)*[sx,sy]
    if len(p0)<8: continue
    F,mask=cv2.findFundamentalMat(p0,p1,RM,fc.MAGSAC_T,0.999,200000)
    mask=np.ones(len(p0),bool) if mask is None else mask.ravel().astype(bool)
    keep=mask&(fc.sampson(fc.F_arkit(i,j),p0,p1)<fc.SAMPSON_T)
    for (x0,y0),(x1,y1) in zip(p0[keep],p1[keep]):
        c0=(i,int(x0//G),int(y0//G)); c1=(j,int(x1//G),int(y1//G))
        node_px[c0].append((x0,y0)); node_px[c1].append((x1,y1)); union(c0,c1)
tracks=defaultdict(lambda: defaultdict(list))
for cell,pxs in node_px.items():
    tracks[find(cell)][cell[0]].append((float(np.mean([q[0] for q in pxs])),float(np.mean([q[1] for q in pxs]))))

# --- triangulate + gates, KEEP observations for floor-band survivors ---
def tri(views):
    A=[]
    for fid,x,y in views:
        P=fc.projmat(fid); A.append(x*P[2]-P[0]); A.append(y*P[2]-P[1])
    _,_,Vt=np.linalg.svd(np.asarray(A)); X=Vt[-1]; return X[:3]/X[3]
pts=[]; obs_of=[]
for root,byf in tracks.items():
    views=[(fid,float(np.mean([q[0] for q in v])),float(np.mean([q[1] for q in v]))) for fid,v in byf.items()]
    if len(views)<2: continue
    X=tri(views); reprojs=[]; dirs=[]; ok=True
    for fid,x,y in views:
        Xc=fc.R_of(fid)@X+fc.t_of(fid); z=Xc[2]
        if not(fc.DEPTH_MIN<z<fc.DEPTH_MAX): ok=False; break
        uv=fc.K_of(fid)@Xc; uv=uv[:2]/uv[2]; reprojs.append(np.hypot(uv[0]-x,uv[1]-y))
        d=X-fc.C_of(fid); dirs.append(d/(np.linalg.norm(d)+1e-12))
    if not ok or max(reprojs)>fc.REPROJ_T: continue
    ang=max([np.degrees(np.arccos(np.clip(dirs[a]@dirs[b],-1,1))) for a in range(len(dirs)) for b in range(a+1,len(dirs))]+[0])
    if ang<fc.TRI_ANGLE_MIN: continue
    if abs(fc.floor_dist(X))<fc.FLOOR_BAND:      # floor-band only (headline overlay)
        pts.append(X); obs_of.append(views)
pts=np.asarray(pts)
print(f"[rescue] floor-band survivors={len(pts)}")

# --- PRODUCTION-faithful colorize: px*scale-0.5, bilinear, avg over obs, round ---
# group observations by frame; sample highres JPEG (fallback work PNG)
obs_by_frame=defaultdict(list)   # fid -> [(pt_idx, x_work, y_work)]
for pi,views in enumerate(obs_of):
    for fid,x,y in views: obs_by_frame[fid].append((pi,x,y))
acc=np.zeros((len(pts),3)); cnt=np.zeros(len(pts))
def bilinear(img,fx,fy):
    x0=int(np.floor(fx)); y0=int(np.floor(fy)); x1=x0+1; y1=y0+1
    h,w=img.shape[:2]
    if x0<0 or y0<0 or x1>=w or y1>=h: return None
    dx=fx-x0; dy=fy-y0
    return ((1-dx)*(1-dy)*img[y0,x0]+dx*(1-dy)*img[y0,x1]+(1-dx)*dy*img[y1,x0]+dx*dy*img[y1,x1])
for fid,lst in obs_by_frame.items():
    p=fc.POSES[fid]
    ip=p.get("img_highres");
    import os
    if ip and os.path.exists(ip):
        scale=p["highres_scale"]   # 3.75, work->highres
    else:
        ip=p["img_work"]; scale=1.0
    if not os.path.exists(ip): continue
    img=np.asarray(Image.open(ip).convert("RGB"),dtype=np.float64)
    for pi,xw,yw in lst:
        fx=xw*scale-0.5; fy=yw*scale-0.5
        c=bilinear(img,fx,fy)
        if c is not None: acc[pi]+=c; cnt[pi]+=1
    del img
valid=cnt>0
rc=np.zeros((len(pts),3),np.uint8)
rc[valid]=np.round(acc[valid]/cnt[valid,None]).clip(0,255).astype(np.uint8)
print(f"[colorize] colored {int(valid.sum())}/{len(pts)} (obs avg, bilinear px*scale-0.5)")
pts=pts[valid]; rc=rc[valid]
fc.write_ply(FR+"/floor_rescue_band_colored.ply", pts, rgb=rc)

# --- load SIFT floor (production RGB) ---
def load_ply_rgb(path):
    import struct
    f=open(path,"rb"); hdr=b""
    while b"end_header\n" not in hdr: hdr+=f.read(1)
    n=next(int(l.split()[-1]) for l in hdr.decode().splitlines() if l.startswith("element vertex"))
    buf=f.read(n*15); xyz=np.zeros((n,3)); rgb=np.zeros((n,3),np.uint8)
    for i in range(n):
        xyz[i]=struct.unpack_from("<fff",buf,i*15); rgb[i]=struct.unpack_from("<BBB",buf,i*15+12)
    return xyz,rgb
sxyz,srgb=load_ply_rgb(FR+"/production_floor.ply")

# --- top-down true-color render ---
nrm=fc.PLANE_N; a=np.array([1.,0,0]);
if abs(nrm@a)>.9: a=np.array([0,0,1.])
u=a-(a@nrm)*nrm; u/=np.linalg.norm(u); v=np.cross(nrm,u)
def to_uv(P): return np.stack([P@u,P@v],1)
suv=to_uv(sxyz); ruv=to_uv(pts)
allu=np.concatenate([suv,ruv]); umin=allu.min(0)-0.1; umax=allu.max(0)+0.1
PPM=260   # px per meter
Wpx=int((umax[0]-umin[0])*PPM); Hpx=int((umax[1]-umin[1])*PPM)
def render(layers, R=3):
    canvas=np.full((Hpx,Wpx,3),18,np.uint8)  # dark bg like viewer
    yy,xx=np.mgrid[-R:R+1,-R:R+1]; disk=(xx*xx+yy*yy)<=R*R
    for uv,col in layers:
        px=((uv-umin)*PPM).astype(int); px[:,1]=Hpx-1-px[:,1]
        for (cx,cy),c in zip(px,col):
            x0,x1=max(0,cx-R),min(Wpx,cx+R+1); y0,y1=max(0,cy-R),min(Hpx,cy+R+1)
            if x0>=x1 or y0>=y1: continue
            dm=disk[(y0-cy+R):(y1-cy+R),(x0-cx+R):(x1-cx+R)]
            canvas[y0:y1,x0:x1][dm]=c
    return canvas
A=render([(suv,srgb)])                          # SIFT only
B=render([(suv,srgb),(ruv,rc)])                 # SIFT + rescue
gap=np.full((Hpx,20,3),40,np.uint8)
combo=np.concatenate([A,gap,B],1)
Image.fromarray(combo).save(FR+"/overlay_floor_truecolor.png")
Image.fromarray(A).save(FR+"/overlay_floor_sift.png")
Image.fromarray(B).save(FR+"/overlay_floor_sift_plus_rescue.png")
print(f"[render] {Wpx}x{Hpx}/panel  PPM={PPM}  -> overlay_floor_truecolor.png (左SIFT | 右SIFT+救援)")
print("DONE")
