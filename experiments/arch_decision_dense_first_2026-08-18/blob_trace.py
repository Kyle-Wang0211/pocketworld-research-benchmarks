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
nfl_d=np.load(S+"/floor.npy"); up=nfl_d[:3]; dfl=nfl_d[3]
nw=np.array([0.46,-0.679,-0.572]); nw/=np.linalg.norm(nw)
u_=np.cross(up,nw); u_/=np.linalg.norm(u_); v_=np.cross(nw,u_)
DW=4.734
idxs=[]
CH=3_000_000
for s in range(0,n,CH):
    d=np.array(M[s:s+CH])
    xyz=np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64)
    r=xyz@nw+DW; pu=xyz@u_; pv=xyz@v_
    m=(r>-0.55)&(r<-0.08)&(pu>-4.2)&(pu<0.2)&(pv>-1.7)&(pv<1.7)
    idxs.append(s+np.nonzero(m)[0])
I=np.concatenate(idxs); print("blob点数",len(I))
np.save(S+"/blob_idx.npy",I)
offs=np.load(S+"/offs.npy")
fi=np.searchsorted(offs,I,side="right")-1
cnt=np.bincount(fi,minlength=132)
top=np.argsort(-cnt)[:8]
print("来源帧 top8:",[(int(t),int(cnt[t])) for t in top])
# 叠加 top4 帧
sel=[int(t) for t in top[:4]]
tiles=[]
for fr in sel:
    mk=np.array(Image.open(f"{BASE}/out_P16k/mask/{fr:08d}_final.png"))>0
    yy,xx=np.nonzero(mk)
    img=np.array(Image.open(f"{BASE}/in_P16k/images/frame_{fr:06d}.jpg").convert("RGB").resize((768,576)))
    m=(I>=offs[fr])&(I<offs[fr+1])
    loc=I[m]-offs[fr]
    img[yy[loc],xx[loc]]=(255,40,40)
    tiles.append(Image.fromarray(img))
G=Image.new("RGB",(768*2,576*2))
for k,im in enumerate(tiles): G.paste(im,(768*(k%2),576*(k//2)))
G.save(S+"/blob_src.jpg",quality=88)
print("sel",sel)
