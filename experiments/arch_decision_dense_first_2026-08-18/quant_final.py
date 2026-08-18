import numpy as np, json, re
from PIL import Image
S="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/wall"
BASE="/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
def stream(p, chunk=3_000_000):
    with open(p,"rb") as f:
        hdr=b""
        while True:
            l=f.readline(); hdr+=l
            if l.strip()==b"end_header": break
        n=int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1]); off=len(hdr)
    M=np.memmap(p,dtype=DT,mode="r",offset=off,shape=(n,))
    for s in range(0,n,chunk):
        d=np.array(M[s:s+chunk])
        yield s,np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)
nfl_d=np.load(S+"/floor.npy"); up=nfl_d[:3]; dfl=nfl_d[3]
nw=np.array([0.46,-0.679,-0.572]); nw/=np.linalg.norm(nw)
u_=np.cross(up,nw); u_/=np.linalg.norm(u_); v_=np.cross(nw,u_)
DW=4.734
paths = {
 "P16k":  BASE+"/dense_P16k.ply",
 "P8k":   BASE+"/aligned_P8k.ply",
 "GTO":   "/Users/kaidongwang/Documents/progecttwo/_host_experiments/gto_dense_20260818/aligned_GTO.ply",
 "P16kH": BASE+"/aligned_P16kH.ply",
 "sparse":"/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/ply_P16KH.ply",
}
print("== 墙后团块口径: u[-4.2,0.2] v[-1.7,1.7], 团块 r[-0.55,-0.08], 墙面 |r|<0.06(不限色)")
blob={}
for k,p in paths.items():
    wn=bn=0; br=[]
    for s,xyz,rgb in stream(p):
        r=xyz@nw+DW; pu=xyz@u_; pv=xyz@v_
        inb=(pu>-4.2)&(pu<0.2)&(pv>-1.7)&(pv<1.7)
        wn+=int((inb&(np.abs(r)<0.06)).sum())
        m=inb&(r>-0.55)&(r<-0.08)
        bn+=int(m.sum()); br.append(r[m])
    br=np.concatenate(br) if br else np.array([0.])
    blob[k]=dict(wall=wn,blob=bn,pct=100*bn/max(wn,1),med=float(np.median(br)))
    print(f"{k:6s} 墙面 {wn:>9,}  墙后团块 {bn:>7,}  = {100*bn/max(wn,1):5.2f}%  团块r中位 {np.median(br):+.3f} gauge")
json.dump(blob,open(S+"/blob_stats.json","w"),indent=1)

# photo 置信度取证 (P16k, top 帧)
def read_pfm(fp):
    with open(fp,"rb") as f:
        assert f.readline().strip()==b"Pf"
        w,h=map(int,f.readline().split())
        scale=float(f.readline())
        data=np.frombuffer(f.read(w*h*4),dtype="<f4" if scale<0 else ">f4").reshape(h,w)
        return np.flipud(data).copy()
offs=np.load(S+"/offs.npy")
I=np.load(S+"/blob_idx.npy")
rows=[]
for fr in [80,79,100,103,86]:
    mk=np.array(Image.open(f"{BASE}/out_P16k/mask/{fr:08d}_final.png"))>0
    yy,xx=np.nonzero(mk)
    m=(I>=offs[fr])&(I<offs[fr+1]); loc=I[m]-offs[fr]
    by,bx=yy[loc],xx[loc]
    confs=[read_pfm(f"{BASE}/out_P16k/conf{i}/{fr:08d}.pfm") for i in range(3)]
    # 对照: 同帧 final mask 内、且3D落在墙面 |r|<0.06 的像素 —— 用之前 idx_A(白墙面)交集
    IA=np.load(S+"/idx_A.npy")
    ma=(IA>=offs[fr])&(IA<offs[fr+1]); la=IA[ma]-offs[fr]
    wy,wx=yy[la],xx[la]
    row=dict(frame=fr,n_blob=len(bx),n_wall=len(wx))
    for i,c in enumerate(confs):
        row[f"conf{i}_blob"]=float(np.median(c[by,bx])) if len(bx) else None
        row[f"conf{i}_wall"]=float(np.median(c[wy,wx])) if len(wx) else None
    rows.append(row)
    print(f"帧{fr}: blob像素 {len(bx)}, 墙面像素 {len(wx)}")
    for i in range(3):
        print(f"   conf{i}  blob中位 {row[f'conf{i}_blob']:.3f}   墙面中位 {row[f'conf{i}_wall']:.3f}")
json.dump(rows,open(S+"/conf_forensics.json","w"),indent=1)
