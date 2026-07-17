import subprocess,types,sys,struct
from pathlib import Path
import numpy as np
REPO=Path("/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714")
REV="f2fc9a1"; SRC="experiments/floor_plane_sweep_densifier_2026-07-13/fr_planesweep_wall_ceiling.py"
payload=subprocess.check_output(["git","-C",str(REPO),"show",f"{REV}:{SRC}"])
m=types.ModuleType("pin"); m.__file__="pin"; sys.modules["pin"]=m
exec(compile(payload,m.__file__,"exec"),m.__dict__)
cap=REPO/"data/pocketworld_captures/cap50"
D=cap/"device_full_pull_2026-07-17"
frames=m.load_frames(cap/"private_manifests/subset_meta_cap50full.json",
                     cap/"private_manifests/sfm_fed_frames.jsonl",
                     cap/"raw/photos_highres")
fbyid={int(f.frame_id):f for f in frames}

def load_l1(fid):
    b=open(D/f"l1_depth_{fid}.bin","rb").read()
    magic,ver,f_,H,W=struct.unpack("<5i",b[:20])
    data=np.frombuffer(b,dtype="<f4",offset=20)
    depth=data[:H*W].reshape(H,W).copy()
    conf=data[H*W:2*H*W].reshape(H,W).copy()
    return depth,conf,H,W

# load union plane-sweep points
def load_ply_ascii(p):
    lines=p.read_text().splitlines()
    i=lines.index("end_header")+1
    rows=[l.split() for l in lines[i:] if l.strip()]
    a=np.array(rows,dtype=float)
    return a
U=load_ply_ascii(REPO/"experiments/u3_merge_prototypes_2026-07-18/05_median_fusion/union_baseline.ply")
xyz=U[:,:3]; nviews=U[:,6]
print("union",xyz.shape,"nviews range",nviews.min(),nviews.max())

for fid in [2,20,83,128,129]:
    depth,conf,H,W=load_l1(fid)
    f=fbyid[fid]
    cam=(f.R@xyz.T).T+f.t
    z=cam[:,2]
    front=z>0.05
    homo=(f.K@cam.T).T
    u=homo[:,0]/z; v=homo[:,1]/z
    sx=W/f.width; sy=H/f.height
    ud=u*sx; vd=v*sy
    inb=front&(ud>=0)&(ud<W-1)&(vd>=0)&(vd<H-1)
    ui=np.clip(np.round(ud).astype(int),0,W-1); vi=np.clip(np.round(vd).astype(int),0,H-1)
    dl1=depth[vi,ui]; cl1=conf[vi,ui]
    resid=z-dl1  # + => candidate behind measured surface(occluded); - => in front(freespace)
    good=inb&(cl1>0.5)
    r=resid[good]
    print(f"fid{fid} inbounds {inb.sum()}/{len(xyz)} conf>0.5&in {good.sum()} resid(m) med {np.median(r):.3f} p10 {np.percentile(r,10):.3f} p90 {np.percentile(r,90):.3f} frac_front(<-0.1) {(r<-0.1).mean():.3f} frac_behind(>0.1) {(r>0.1).mean():.3f}")
