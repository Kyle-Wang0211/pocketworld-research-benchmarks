import numpy as np, json
S="/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad/wall"
DT = np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
def stream(p, chunk=2_000_000):
    with open(p,"rb") as f:
        hdr=b""
        while True:
            l=f.readline(); hdr+=l
            if l.strip()==b"end_header": break
        n=int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1]); off=len(hdr)
    M=np.memmap(p,dtype=DT,mode="r",offset=off,shape=(n,))
    for s in range(0,n,chunk):
        d=np.array(M[s:s+chunk])
        yield np.stack([d["x"],d["y"],d["z"]],1).astype(np.float64), np.stack([d["r"],d["g"],d["b"]],1)

nfl_d=np.load(S+"/floor.npy"); up=nfl_d[:3]; dfl=nfl_d[3]
nw=np.array([0.46,-0.679,-0.572]); nw/=np.linalg.norm(nw)
u=np.cross(up,nw); u/=np.linalg.norm(u); v=np.cross(nw,u)
DW=4.734; ULO,UHI,VLO,VHI=-3.95,1.45,-1.85,2.40

def collect(p, white_only=True, slab=0.15):
    xs=[]; cs=[]
    for xyz,rgb in stream(p):
        mx=rgb.max(1).astype(float); mn=rgb.min(1).astype(float)
        m=(np.abs(xyz@nw+DW)<slab)
        pu=xyz@u; pv=xyz@v
        m&=(pu>ULO)&(pu<UHI)&(pv>VLO)&(pv<VHI)&((xyz@up+dfl)>0.15)
        if white_only:
            m&=(mx/255>0.55)&((mx-mn)/np.maximum(mx,1)<0.28)
        xs.append(xyz[m]); cs.append(rgb[m])
    return np.concatenate(xs), np.concatenate(cs)

def robust_plane(P, rounds=3):
    n0,d0=nw.copy(),DW
    keep=np.ones(len(P),bool)
    for _ in range(rounds):
        Q=P[keep]; c=Q.mean(0)
        w,Vt=np.linalg.eigh(np.cov((Q-c).T))
        nv=Vt[:,0];
        if nv@nw<0: nv=-nv
        d=-nv@c
        r=P@nv+d
        mad=np.median(np.abs(r[keep]-np.median(r[keep])))
        keep=np.abs(r-np.median(r[keep]))<max(3*1.4826*mad,0.01)
    Q=P[keep]; c=Q.mean(0)
    w,Vt=np.linalg.eigh(np.cov((Q-c).T))
    nv=Vt[:,0]
    if nv@nw<0: nv=-nv
    return nv,-nv@c,keep

def band_profile(P, nv, d, axis, nb=5):
    t=P@axis; r=P@nv+d
    qs=np.linspace(t.min(),t.max(),nb+1)
    ctr=[]; mu=[]; se=[]
    for i in range(nb):
        m=(t>=qs[i])&(t<qs[i+1])
        if m.sum()<20: ctr.append(np.nan); mu.append(np.nan); se.append(np.nan); continue
        ctr.append((qs[i]+qs[i+1])/2); mu.append(float(np.mean(r[m]))); se.append(float(np.std(r[m])/np.sqrt(m.sum())))
    return np.array(ctr),np.array(mu),np.array(se)

paths = {
 "P16k":  "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/dense_P16k.ply",
 "P8k":   "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/aligned_P8k.ply",
 "GTO":   "/Users/kaidongwang/Documents/progecttwo/_host_experiments/gto_dense_20260818/aligned_GTO.ply",
 "P16kH": "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/aligned_P16kH.ply",
 "sparse":"/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/ply_P16KH.ply",
}
res={}
for k,p in paths.items():
    P,C=collect(p)
    if k=="sparse":
        P2,C2=collect(p,white_only=False)
        print(f"sparse: white口径 {len(P)} 点 / 不限色 {len(P2)} 点")
    nv,d,keep=robust_plane(P)
    r=P@nv+d
    rk=r[keep]
    prof_u=band_profile(P[keep],nv,d,u)
    prof_v=band_profile(P[keep],nv,d,v)
    # 相对参考平面(P16k 自身平面)的分带 — 之后统一算
    res[k]=dict(n=len(P),nkeep=int(keep.sum()),nv=nv.tolist(),d=float(d),
                rms=float(np.sqrt(np.mean(rk**2))),
                p90=float(np.percentile(np.abs(rk),90)),
                prof_u_ctr=prof_u[0].tolist(),prof_u_mu=prof_u[1].tolist(),prof_u_se=prof_u[2].tolist(),
                prof_v_ctr=prof_v[0].tolist(),prof_v_mu=prof_v[1].tolist(),prof_v_se=prof_v[2].tolist())
    np.save(S+f"/crop_{k}_xyz.npy",P); np.save(S+f"/crop_{k}_rgb.npy",C)
    print(k, "点数",len(P), "trim后",int(keep.sum()), "RMS(gauge)",round(res[k]["rms"],4))

# 法向两两夹角
ks=list(res)
print("\n法向两两夹角(度):")
for i in range(len(ks)):
    for j in range(i+1,len(ks)):
        a=np.array(res[ks[i]]["nv"]); b=np.array(res[ks[j]]["nv"])
        ang=np.degrees(np.arccos(np.clip(abs(a@b),-1,1)))
        print(f"  {ks[i]:6s} vs {ks[j]:6s}: {ang:.3f}")
json.dump(res,open(S+"/measure_wall.json","w"),indent=1)
