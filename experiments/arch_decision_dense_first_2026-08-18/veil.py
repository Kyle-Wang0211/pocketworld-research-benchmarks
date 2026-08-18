import numpy as np, json
S="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/wall"
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
        yield s, np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)
nfl_d=np.load(S+"/floor.npy"); up=nfl_d[:3]; dfl=nfl_d[3]
nw=np.array([0.46,-0.679,-0.572]); nw/=np.linalg.norm(nw)
u=np.cross(up,nw); u/=np.linalg.norm(u); v=np.cross(nw,u)
DW=4.734
def masks(xyz,rgb):
    mx=rgb.max(1).astype(float); mn=rgb.min(1).astype(float)
    white=(mx/255>0.55)&((mx-mn)/np.maximum(mx,1)<0.28)
    r=xyz@nw+DW; pu=xyz@u; pv=xyz@v
    inb=(pu>-3.9)&(pu<1.1)&(pv>-1.0)&(pv<2.4)&white
    wall=inb&(np.abs(r)<0.06)
    veil=inb&(r>0.08)&(r<0.55)
    return wall,veil,r
paths = {
 "P16k":  "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/dense_P16k.ply",
 "P8k":   "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/aligned_P8k.ply",
 "GTO":   "/Users/kaidongwang/Documents/progecttwo/_host_experiments/gto_dense_20260818/aligned_GTO.ply",
 "P16kH": "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/aligned_P16kH.ply",
 "sparse":"/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/ply_P16KH.ply",
}
out={}
veil_idx_P16k=[]
for k,p in paths.items():
    wn=vn=0; vr=[]
    for s,xyz,rgb in stream(p):
        wall,veil,r=masks(xyz,rgb)
        wn+=int(wall.sum()); vn+=int(veil.sum()); vr.append(r[veil])
        if k=="P16k": veil_idx_P16k.append(s+np.nonzero(veil)[0])
    vr=np.concatenate(vr) if vr else np.array([])
    out[k]=dict(wall=wn,veil=vn,ratio=vn/max(wn,1),vr_med=float(np.median(vr)) if len(vr) else None)
    print(f"{k:6s} 墙面点(|r|<0.06) {wn:>9,}  雾帘点(0.08<r<0.55) {vn:>9,}  帘/墙 {vn/max(wn,1)*100:6.2f}%  帘r中位 {out[k]['vr_med']}")
I=np.concatenate(veil_idx_P16k); np.save(S+"/veil_idx_P16k.npy",I)
json.dump(out,open(S+"/veil_stats.json","w"),indent=1)
# P16k 雾帘溯源:帧分布
offs=np.load(S+"/offs.npy")
fi=np.searchsorted(offs,I,side="right")-1
cnt=np.bincount(fi,minlength=132)
top=np.argsort(-cnt)[:10]
print("\nP16k 雾帘点来源帧 top10:", [(int(t),int(cnt[t])) for t in top])
print("贡献>1000点的帧数:", int((cnt>1000).sum()))
