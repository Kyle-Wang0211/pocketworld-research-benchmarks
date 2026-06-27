import numpy as np, struct, os
from collections import defaultdict
from PIL import Image
np.random.seed(0)
import sys
OUT=sys.argv[1] if len(sys.argv)>1 else '/tmp/batch_out2'
PLY=sys.argv[2] if len(sys.argv)>2 else '/Users/kaidongwang/Desktop/tiled_414_viewer/cloud_batch224k.ply'
IMGDIR='/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/device_captures/app_documents_latest/cap_1779949415373229/photos_highres'

# 1) points3D.txt -> id->xyz
id2xyz={}
for line in open(OUT+'/points3D.txt'):
    if line[0]=='#' or not line.strip(): continue
    v=line.split(); id2xyz[int(v[0])]=(float(v[1]),float(v[2]),float(v[3]))
print('points3D:', len(id2xyz))

# 2) images.txt -> point3D_id -> first (image_name, x, y)
id2obs={}
hdr=None
for line in open(OUT+'/images.txt'):
    if line[0]=='#' or not line.strip(): continue
    p=line.split()
    if hdr is None:
        hdr=p[-1]
    else:
        for k in range(0,len(p)-2,3):
            pid=int(p[k+2])
            if pid!=-1 and pid not in id2obs:
                id2obs[pid]=(hdr,float(p[k]),float(p[k+1]))
        hdr=None
print('observed pts:', len(id2obs))

# 3) sample colors (open each JPEG once)
by_img=defaultdict(list)
for pid,(name,x,y) in id2obs.items(): by_img[name].append((pid,x,y))
colors={}
for name,lst in by_img.items():
    path=os.path.join(IMGDIR,name)
    if not os.path.exists(path): continue
    im=np.asarray(Image.open(path).convert('RGB')); H,W=im.shape[:2]
    for pid,x,y in lst:
        xi=min(W-1,max(0,int(round(x)))); yi=min(H-1,max(0,int(round(y))))
        colors[pid]=im[yi,xi]
print('colored:', len(colors))

# 4) write full colored PLY
ids=[i for i in id2xyz if i in colors]
with open(PLY,'wb') as f:
    f.write(b'ply\nformat binary_little_endian 1.0\n')
    f.write(('element vertex %d\n'%len(ids)).encode())
    f.write(b'property float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
    for i in ids:
        x,y,z=id2xyz[i]; r,g,b=colors[i]
        f.write(struct.pack('<fffBBB',float(x),float(y),float(z),int(r),int(g),int(b)))
print('WROTE', len(ids), 'colored points ->', PLY)

# 5) FULL 224k scatter (RANSAC model on 20k subsample, std on FULL)
P=np.array([id2xyz[i] for i in id2xyz],np.float32); n=len(P)
def fitS(pts):
    A=np.c_[2*pts,np.ones(len(pts))];b=(pts**2).sum(1);c,*_=np.linalg.lstsq(A,b,rcond=None);ct=c[:3];return ct,np.sqrt(max(1e-9,c[3]+(ct**2).sum()))
span=np.percentile(np.linalg.norm(P-np.median(P,0),axis=1),90)
sub=P[np.random.choice(n,20000,replace=False)]
best=None;bn=0
for _ in range(2500):
    ix=np.random.choice(len(sub),4,replace=False)
    try:ct,rad=fitS(sub[ix])
    except:continue
    if not(span*0.02<rad<span*0.30):continue
    d=np.abs(np.linalg.norm(sub-ct,axis=1)-rad);s=int((d<0.06*rad).sum())
    if s>bn:bn=s;best=(ct,rad)
ct,rad=best
for _ in range(4):
    d=np.abs(np.linalg.norm(P-ct,axis=1)-rad);inl=d<0.06*rad;ct,rad=fitS(P[inl])
d=np.abs(np.linalg.norm(P-ct,axis=1)-rad);gi=d<0.08*rad;gstd=d[gi].std()
sub=P[np.random.choice(n,20000,replace=False)];best=None;bn=0
for _ in range(3000):
    ix=np.random.choice(len(sub),3,replace=False);p0,p1,p2=sub[ix];nr=np.cross(p1-p0,p2-p0);ln=np.linalg.norm(nr)
    if ln<1e-9:continue
    nr/=ln;dist=np.abs((sub-p0)@nr);s=int((dist<0.01*span).sum())
    if s>bn:bn=s;best=(nr,p0)
nr,p0=best
for _ in range(4):
    dist=np.abs((P-p0)@nr);inl=dist<0.01*span;Q=P[inl];c=Q.mean(0);u,sv,vt=np.linalg.svd(Q-c,full_matrices=False);nr=vt[2];p0=c
dist=np.abs((P-p0)@nr);pi=dist<0.02*span;pstd=dist[pi].std()
print(f'FULL224K 纯血COLMAP全批: 全{n}点 | 地球仪球壳 {gstd:.4f} ({100*gstd/span:.2f}%span) 内点{int(gi.sum())} | 地板 {pstd:.4f} ({100*pstd/span:.2f}%span) 内点{int(pi.sum())}')
