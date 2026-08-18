import numpy as np
from PIL import Image
S="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/wall"
BASE="/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
p=BASE+"/dense_P16k.ply"
with open(p,"rb") as f:
    hdr=b""
    while True:
        l=f.readline(); hdr+=l
        if l.strip()==b"end_header": break
    n=int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1]); off=len(hdr)
M=np.memmap(p,dtype=DT,mode="r",offset=off,shape=(n,))
offs=np.load(S+"/offs.npy"); refs=np.load(S+"/refs.npy")
nfl_d=np.load(S+"/floor.npy"); up=nfl_d[:3]; dfl=nfl_d[3]
nw=np.array([0.46,-0.679,-0.572]); nw/=np.linalg.norm(nw)
u=np.cross(up,nw); u/=np.linalg.norm(u); v=np.cross(nw,u)

def predicate(xyz,rgb,dwall,ulo,uhi,vlo,vhi):
    mx=rgb.max(1).astype(float); mn=rgb.min(1).astype(float)
    white=(mx/255>0.55)&((mx-mn)/np.maximum(mx,1)<0.28)
    h=xyz@up+dfl
    pu=xyz@u; pv=xyz@v
    return white&(h>0.15)&(np.abs(xyz@nw+dwall)<0.06)&(pu>ulo)&(pu<uhi)&(pv>vlo)&(pv<vhi)

conds={"A":(4.734,-3.95,1.45,-1.90,2.45),"B":(4.327,1.15,8.85,-1.95,0.90)}
idxs={k:[] for k in conds}
CH=2_000_000
for s in range(0,n,CH):
    d=np.array(M[s:s+CH])
    xyz=np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64)
    rgb=np.stack([d["r"],d["g"],d["b"]],1)
    for k,c in conds.items():
        m=predicate(xyz,rgb,*c)
        idxs[k].append(s+np.nonzero(m)[0])
for k in conds:
    I=np.concatenate(idxs[k]); np.save(S+f"/idx_{k}.npy",I)
    # 每帧命中数
    fi=np.searchsorted(offs,I,side="right")-1
    cnt=np.bincount(fi,minlength=132)
    top=np.argsort(-cnt)[:6]
    print(k,"总点",len(I),"命中最多帧:",[(int(refs[t]),int(cnt[t])) for t in top])
