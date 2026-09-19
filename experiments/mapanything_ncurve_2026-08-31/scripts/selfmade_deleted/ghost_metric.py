# 重影厚度:视图 j 的世界点 → 投进视图 i → 与 i 自己的深度比 |Δz|/z。
# 只取「两视图都判有效 + 投影落在画面内 + 深度同量级」的像素,取中位数(抗遮挡外点)。
import numpy as np,itertools,sys
def load(t):
    z=np.load(f"dpk_{t}.npz"); return z["D"].astype(np.float32),z["M"],z["K"],z["P"]
def world(D,K,P):
    H,W=D.shape[-2:]; v,u=np.mgrid[0:H,0:W].astype(np.float32)
    def one(d,k,p):
        x=(u-k[0,2])/k[0,0]*d; y=(v-k[1,2])/k[1,1]*d
        c=np.stack([x,y,d],-1)
        return c@p[:3,:3].T+p[:3,3]
    return one
for t in ("unposed","mvconf"):
    D,M,K,P=load(t); n,H,W=D.shape; one=world(D,K,P)
    # 相机中心两两距离 → 选最近邻对(重叠最多)
    C=P[:,:3,3]; dist=np.linalg.norm(C[:,None]-C[None],axis=-1); np.fill_diagonal(dist,1e9)
    pairs=[(i,int(np.argmin(dist[i]))) for i in range(n)]
    rel=[]
    for i,j in pairs:
        Wj=one(D[j],K[j],P[j])                       # j 的世界点
        Pi=np.linalg.inv(P[i]); Cj=Wj@Pi[:3,:3].T+Pi[:3,3]   # 变到 i 相机系
        z=Cj[...,2]; ok=M[j]&(z>1e-6)
        uu=K[i][0,0]*Cj[...,0]/np.where(z==0,1,z)+K[i][0,2]
        vv=K[i][1,1]*Cj[...,1]/np.where(z==0,1,z)+K[i][1,2]
        ui=np.round(uu).astype(int); vi=np.round(vv).astype(int)
        ok&=(ui>=0)&(ui<W)&(vi>=0)&(vi<H)
        if ok.sum()<200: continue
        zi=D[i][np.clip(vi,0,H-1),np.clip(ui,0,W-1)]; mi=M[i][np.clip(vi,0,H-1),np.clip(ui,0,W-1)]
        ok&=mi&(zi>1e-6)
        if ok.sum()<200: continue
        r=np.abs(z[ok]-zi[ok])/zi[ok]
        r=r[r<0.5]                                    # 剔遮挡(不同表面)只留同表面分歧
        if r.size>200: rel.append((np.median(r),ok.sum()))
    v=np.array([x[0] for x in rel])
    print(f"{t:8s}  邻对 {len(rel):3d}/{n}   重影厚度中位 {np.median(v)*100:.2f}%   "
          f"p25 {np.percentile(v,25)*100:.2f}%  p75 {np.percentile(v,75)*100:.2f}%",flush=True)
