#!/usr/bin/env python3
"""MVSNet cams/*.txt -> COLMAP sparse/{cameras,images,points3D}.bin (one PINHOLE camera per image; image index
order == the order delaunay_mesher assigns, which is what fused.ply.vis refers to)."""
import sys, struct, glob, os, numpy as np
SRC, WS, W, H = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
os.makedirs(f"{WS}/sparse", exist_ok=True)
def rot2quat(R):
    q = np.empty(4); t = np.trace(R)
    if t > 0: s = np.sqrt(t+1)*2; q[:] = [0.25*s,(R[2,1]-R[1,2])/s,(R[0,2]-R[2,0])/s,(R[1,0]-R[0,1])/s]
    elif R[0,0] > R[1,1] and R[0,0] > R[2,2]: s = np.sqrt(1+R[0,0]-R[1,1]-R[2,2])*2; q[:] = [(R[2,1]-R[1,2])/s,0.25*s,(R[0,1]+R[1,0])/s,(R[0,2]+R[2,0])/s]
    elif R[1,1] > R[2,2]: s = np.sqrt(1+R[1,1]-R[0,0]-R[2,2])*2; q[:] = [(R[0,2]-R[2,0])/s,(R[0,1]+R[1,0])/s,0.25*s,(R[1,2]+R[2,1])/s]
    else: s = np.sqrt(1+R[2,2]-R[0,0]-R[1,1])*2; q[:] = [(R[1,0]-R[0,1])/s,(R[0,2]+R[2,0])/s,(R[1,2]+R[2,1])/s,0.25*s]
    return q/np.linalg.norm(q)
cams = sorted(glob.glob(f"{SRC}/cams/*_cam.txt")); recs = []
for i, p in enumerate(cams):
    L = [l.rstrip() for l in open(p)]
    E = np.fromstring(" ".join(L[1:5]), sep=" ").reshape(4,4); K = np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3,3)
    recs.append((i+1, K, rot2quat(E[:3,:3]), E[:3,3], os.path.basename(p)[:8] + ".jpg"))
with open(f"{WS}/sparse/cameras.bin","wb") as f:
    f.write(struct.pack("<Q", len(recs)))
    for cid,K,_,_,_ in recs:
        f.write(struct.pack("<ii",cid,1)); f.write(struct.pack("<QQ",W,H)); f.write(struct.pack("<4d",K[0,0],K[1,1],K[0,2],K[1,2]))
with open(f"{WS}/sparse/images.bin","wb") as f:
    f.write(struct.pack("<Q", len(recs)))
    for iid,_,q,t,name in recs:
        f.write(struct.pack("<i",iid)); f.write(struct.pack("<4d",*q)); f.write(struct.pack("<3d",*t)); f.write(struct.pack("<i",iid))
        f.write(name.encode()+b"\x00"); f.write(struct.pack("<Q",0))
open(f"{WS}/sparse/points3D.bin","wb").write(struct.pack("<Q",0))
print("sparse written:", len(recs), "images", W, "x", H)
