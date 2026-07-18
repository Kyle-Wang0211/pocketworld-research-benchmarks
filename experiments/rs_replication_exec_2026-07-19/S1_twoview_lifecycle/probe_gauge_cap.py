#!/usr/bin/env python3.11
"""Parameterized gauge probe (generalizes probe_gauge.py, which was cap50-hardcoded).
Verifies delivered PLY frame == meta refined-pose frame (same gauge, no hidden rotation).
Method: rebuild >=3-view tracks from db two_view_geometries, DLT-triangulate with refined
meta poses, NN-match to delivered PLY, fit rotation-only + rot+trans Kabsch.
Same-gauge criterion: rotation angle ~0 deg AND alignment does not reduce residuals.
Diagnostic only; writes probe npy into <cap>/ subdir. Usage: probe_gauge_cap.py cap51
"""
import sqlite3, numpy as np, json, sys, os
from collections import defaultdict
from scipy.spatial import cKDTree

ROOT = "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714"
cap = sys.argv[1]
D = f"{ROOT}/data/pocketworld_captures/{cap}/device_full_pull_2026-07-17"
OUT = f"{ROOT}/experiments/rs_replication_exec_2026-07-19/S1_twoview_lifecycle/{cap}"
os.makedirs(OUT, exist_ok=True)
MAX_IMAGE_ID = 2147483647

def quat_to_R(q):
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)],
                     [2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)],
                     [2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)]])

db=sqlite3.connect(f"file:{D}/sfm_live.db?mode=ro",uri=True);c=db.cursor()
kp_xy={};kp_count={}
for iid,r,cols,data in c.execute("SELECT image_id,rows,cols,data FROM keypoints"):
    a=np.frombuffer(data,np.float32).reshape(r,cols);kp_xy[iid]=a[:,:2].astype(float);kp_count[iid]=r
params=np.frombuffer(c.execute("SELECT params FROM cameras LIMIT 1").fetchone()[0],np.float64)
f_,cx_,cy_=params;K=np.array([[f_,0,cx_],[0,f_,cy_],[0,0,1]])
img_ids=sorted(kp_xy)
offset={};acc=0
for iid in img_ids: offset[iid]=acc;acc+=kp_count[iid]
N=acc
parent=np.arange(N,dtype=np.int64)
def find(x):
    r=x
    while parent[r]!=r:r=parent[r]
    while parent[x]!=r:parent[x],x=r,parent[x]
    return r
for pair_id,r,cols,data in c.execute("SELECT pair_id,rows,cols,data FROM two_view_geometries WHERE rows>0"):
    i1,i2=pair_id//MAX_IMAGE_ID,pair_id%MAX_IMAGE_ID
    if i1 not in offset or i2 not in offset:continue
    m=np.frombuffer(data,np.uint32).reshape(r,cols)
    for f1,f2 in m:
        if f1>=kp_count[i1] or f2>=kp_count[i2]:continue
        ra,rb=find(offset[i1]+int(f1)),find(offset[i2]+int(f2))
        if ra!=rb:parent[rb]=ra
db.close()
for x in range(N):find(x)
meta=json.load(open(f"{D}/sfm_sparse_meta.json"))
assert meta.get('refined') is True
pose={}
for p in meta['poses']:
    if p.get('registered'):
        R=quat_to_R(np.array(p['quat_wxyz']));t=np.array(p['t'])
        pose[p['frame_id']]=(R,t)
off_arr=np.array([offset[i] for i in img_ids]+[N])
iid_arr=np.array(img_ids)
node_img=np.searchsorted(off_arr,np.arange(N),side='right')-1
members=defaultdict(list)
uniq,counts=np.unique(parent,return_counts=True)
big=set(uniq[counts>=3].tolist())
for node in range(N):
    rt=parent[node]
    if rt in big: members[rt].append(node)
pos=[];res_all=[]
Pm={fid:K@np.hstack([R, t.reshape(3,1)]) for fid,(R,t) in pose.items()}
for rt,nodes in members.items():
    A=[];obs=[]
    for nd in nodes:
        iid=int(iid_arr[node_img[nd]]);fid=iid-1
        if fid not in pose:continue
        xy=kp_xy[iid][nd-offset[iid]]
        P=Pm[fid];A.append(xy[0]*P[2]-P[0]);A.append(xy[1]*P[2]-P[1]);obs.append((fid,xy))
    if len(A)<6:continue
    A=np.array(A)
    _,_,Vt=np.linalg.svd(A);X=Vt[-1]
    if abs(X[3])<1e-12:continue
    X=X[:3]/X[3]
    rs=[]
    for fid,xy in obs:
        R,t=pose[fid];Xc=R@X+t
        if Xc[2]<=0: rs=[1e9];break
        pr=K@Xc;rs.append(np.hypot(pr[0]/pr[2]-xy[0],pr[1]/pr[2]-xy[1]))
    res_all.append(np.median(rs));pos.append(X)
pos=np.array(pos);res_all=np.array(res_all)
good=res_all<2.0
print(f"[{cap}] multiview tracks:",len(pos),"median reproj(px):",round(float(np.median(res_all)),4),"frac<2px:",round(float(good.mean()),4))
pos=pos[good]
with open(f"{D}/sfm_sparse.ply","rb") as f:
    h=b""
    while not h.endswith(b"end_header\n"):h+=f.readline()
    n=int([l for l in h.decode().splitlines() if l.startswith("element vertex")][0].split()[-1])
    rec=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
    dt=np.fromfile(f,dtype=rec,count=n)
xyz=np.stack([dt["x"],dt["y"],dt["z"]],1).astype(float)
tree=cKDTree(xyz)
dist,idx=tree.query(pos,k=1,workers=-1)
print("NN dist before: p50",round(float(np.percentile(dist,50)),5),"p90",round(float(np.percentile(dist,90)),5))
sel=dist<0.05
A=pos[sel];B=xyz[idx[sel]]
H=A.T@B
U,S,Vt=np.linalg.svd(H)
Rk=Vt.T@U.T
if np.linalg.det(Rk)<0:
    Vt2=Vt.copy();Vt2[-1]*=-1;Rk=Vt2.T@U.T
ang=np.degrees(np.arccos(np.clip((np.trace(Rk)-1)/2,-1,1)))
A2=(Rk@A.T).T
d2=np.linalg.norm(A2-B,axis=1)
print("rotation-only: angle_deg",round(float(ang),4),"resid p50",round(float(np.percentile(d2,50)),5),"p90",round(float(np.percentile(d2,90)),5))
ca,cb=A.mean(0),B.mean(0)
H=(A-ca).T@(B-cb);U,S,Vt=np.linalg.svd(H);Rk2=Vt.T@U.T
if np.linalg.det(Rk2)<0:
    Vt2=Vt.copy();Vt2[-1]*=-1;Rk2=Vt2.T@U.T
ang2=np.degrees(np.arccos(np.clip((np.trace(Rk2)-1)/2,-1,1)))
t2=cb-Rk2@ca
A3=(Rk2@A.T).T+t2
d3=np.linalg.norm(A3-B,axis=1)
print("rot+trans: angle_deg",round(float(ang2),4),"t",np.round(t2,4),"resid p50",round(float(np.percentile(d3,50)),5),"p90",round(float(np.percentile(d3,90)),5))
np.save(f"{OUT}/probe_R.npy",Rk2);np.save(f"{OUT}/probe_t.npy",t2);np.save(f"{OUT}/probe_R_noT.npy",Rk)
