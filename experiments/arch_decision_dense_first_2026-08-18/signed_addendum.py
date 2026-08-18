# 补充: 有符号评分 s = d_prior - d_MVS (偏移层=缩进=正) 的逐帧 AUC + 工作点, gateA 口径
import numpy as np, json
from PIL import Image
from scipy.spatial import Delaunay
from scipy.stats import rankdata
BASE="/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
WALL="/Users/kaidongwang/Documents/progecttwo/_artifacts/wall_forensics_20260818"
SPARSE_PLY="/Users/kaidongwang/Documents/progecttwo/_artifacts/lightglue_spike/ply_P16KH.ply"
FRAMES=[78,79,80,81,82,83,85,86,87,100,103,107,125]
S768=768/4032.0; CM=42.0
TAUS=[0.5,1.0,1.5,2.0,2.5,3.0,3.5,4.0,5.0,6.0,8.0,10.0]
def read_cam(fr):
    L=open(f"{BASE}/mvs_P16k/cams/{fr:08d}_cam.txt").read().split("\n")
    return np.array([[float(x) for x in L[i+1].split()] for i in range(4)]), np.array([[float(x) for x in L[i+7].split()] for i in range(3)])
def read_pfm(fp):
    with open(fp,"rb") as f:
        assert f.readline().strip()==b"Pf"
        w,h=map(int,f.readline().split()); sc=float(f.readline())
        return np.flipud(np.frombuffer(f.read(w*h*4),dtype="<f4" if sc<0 else ">f4").reshape(h,w)).copy()
def read_ply(fp):
    with open(fp,"rb") as f:
        hdr=b""
        while True:
            l=f.readline(); hdr+=l
            if l.strip()==b"end_header": break
        n=int([x for x in hdr.split(b"\n") if x.startswith(b"element vertex")][0].split()[-1])
        DT=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
        M=np.frombuffer(f.read(n*DT.itemsize),dtype=DT)
    return np.stack([M["x"],M["y"],M["z"]],1).astype(np.float64)
def auc(pos,neg):
    if not len(pos) or not len(neg): return None
    sc=np.concatenate([pos,neg]); rk=rankdata(sc); n1,n0=len(pos),len(neg)
    return float((rk[:n1].sum()-n1*(n1+1)/2)/(n1*n0))
nfl=np.load(WALL+"/floor.npy"); up=nfl[:3]
nw=np.array([0.46,-0.679,-0.572]); nw/=np.linalg.norm(nw)
u_=np.cross(up,nw); u_/=np.linalg.norm(u_); v_=np.cross(nw,u_); DW=4.734
offs=np.load(WALL+"/offs.npy"); blobI=np.load(WALL+"/blob_idx.npy")
SPTS=read_ply(SPARSE_PLY)
res={}; wp={t:dict(det=0,tb=0,kill=0,tc=0) for t in TAUS}
for fr in FRAMES:
    E,Kfull=read_cam(fr); R,t=E[:3,:3],E[:3,3]
    D=read_pfm(f"{BASE}/out_P16k/depth_est/{fr:08d}.pfm")
    mk=np.array(Image.open(f"{BASE}/out_P16k/mask/{fr:08d}_final.png"))>0
    H,W=D.shape; Ks=Kfull.copy(); Ks[:2]*=S768
    XC=SPTS@R.T+t; z=XC[:,2]; ok=z>0.5
    px=XC[ok,0]/z[ok]*Kfull[0,0]+Kfull[0,2]; py=XC[ok,1]/z[ok]*Kfull[1,1]+Kfull[1,2]; zin=z[ok]
    inim=(px>=0)&(px<4032)&(py>=0)&(py<3024); px,py,zin=px[inim],py[inim],zin[inim]
    ix=np.clip((px*S768).astype(int),0,W-1); iy=np.clip((py*S768).astype(int),0,H-1)
    dm=D[iy,ix]; vis=(dm>0)&(np.abs(zin-dm)/np.maximum(dm,1e-6)<0.15)
    gx,gy,za=px[vis]*S768,py[vis]*S768,zin[vis]
    tri=Delaunay(np.stack([gx,gy],1)); simp=tri.simplices; zv=za[simp]
    good_a=(zv.max(1)-zv.min(1))/zv.min(1)<=0.15
    yy,xx=np.nonzero(mk); dpx=D[yy,xx].astype(np.float64)
    Ppix=np.stack([xx,yy],1).astype(np.float64); s=tri.find_simplex(Ppix)
    d_prior=np.full(len(xx),np.nan); ci=np.nonzero(s>=0)[0]; sc_=s[ci]
    T=tri.transform[sc_]; b2=np.einsum('ijk,ik->ij',T[:,:2,:],Ppix[ci]-T[:,2,:])
    w3=np.concatenate([b2,1-b2.sum(1,keepdims=True)],1)
    d_prior[ci]=1.0/np.einsum('ij,ij->i',w3,(1.0/zv)[sc_])
    valid=(s>=0)&np.where(s>=0,good_a[np.maximum(s,0)],False)
    m=(blobI>=offs[fr])&(blobI<offs[fr+1]); loc=blobI[m]-offs[fr]
    ptc=np.stack([(xx-Ks[0,2])/Ks[0,0],(yy-Ks[1,2])/Ks[1,1],np.ones(len(xx))],1)
    XW=(ptc*dpx[:,None]-t)@R; rr=XW@nw+DW; puw=XW@u_; pvw=XW@v_
    clean=(puw>-4.2)&(puw<0.2)&(pvw>-1.7)&(pvw<1.7)&(np.abs(rr)<0.06)
    neg_i=np.nonzero(clean)[0]
    ssc=d_prior-dpx   # 有符号: 缩进为正
    pos_sc=ssc[loc][valid[loc]]; neg_sc=ssc[neg_i][valid[neg_i]]
    res[fr]=dict(auc_signed=round(auc(pos_sc,neg_sc),4) if len(pos_sc) and len(neg_sc) else None,
                 blob_smed_cm=round(float(np.median(pos_sc))*CM,2) if len(pos_sc) else None,
                 clean_smed_cm=round(float(np.median(neg_sc))*CM,2) if len(neg_sc) else None)
    for tau in TAUS:
        th=tau/CM
        wp[tau]["det"]+=int((pos_sc>th).sum()); wp[tau]["tb"]+=len(loc)
        wp[tau]["kill"]+=int((neg_sc>th).sum()); wp[tau]["tc"]+=len(neg_i)
    print(fr,res[fr],flush=True)
aucs=[v["auc_signed"] for v in res.values() if v["auc_signed"] is not None]
print("signed AUC med/min/max",round(float(np.median(aucs)),4),round(min(aucs),4),round(max(aucs),4))
tbl=[dict(tau_cm=t,eff_recall=round(wp[t]["det"]/wp[t]["tb"],4),eff_kill=round(wp[t]["kill"]/wp[t]["tc"],4)) for t in TAUS]
for w in tbl: print(w)
json.dump(dict(per_frame={str(k):v for k,v in res.items()},working_points=tbl),
          open("/Users/kaidongwang/Documents/progecttwo/_artifacts/delaunay_prior_20260818/signed_addendum.json","w"),indent=1)
