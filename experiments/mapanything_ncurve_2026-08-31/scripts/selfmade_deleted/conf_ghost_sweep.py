# 扫官方 confidence_percentile:重影厚度 vs 保留率。用离线保存的 mvconf 置信度重算,不重推理。
import numpy as np
z=np.load("dpk_mvconf.npz"); D=z["D"].astype(np.float32); M=z["M"]; K=z["K"]; P=z["P"]; C=z["C"].astype(np.float32)
n,H,W=D.shape
u,v=np.meshgrid(np.arange(W,dtype=np.float32),np.arange(H,dtype=np.float32))
Cn=P[:,:3,3]; dist=np.linalg.norm(Cn[:,None]-Cn[None],axis=-1); np.fill_diagonal(dist,1e9)
pairs=[(i,int(np.argmin(dist[i]))) for i in range(n)]
def ghost(Mk):
    rel=[]
    for i,j in pairs:
        d=D[j]; k=K[j]; p=P[j]
        x=(u-k[0,2])/k[0,0]*d; y=(v-k[1,2])/k[1,1]*d
        Wj=np.stack([x,y,d],-1)@p[:3,:3].T+p[:3,3]
        Pi=np.linalg.inv(P[i]); Cj=Wj@Pi[:3,:3].T+Pi[:3,3]; zz=Cj[...,2]
        ok=Mk[j]&(zz>1e-6)
        zs=np.where(zz==0,1,zz)
        ui=np.round(K[i][0,0]*Cj[...,0]/zs+K[i][0,2]).astype(int)
        vi=np.round(K[i][1,1]*Cj[...,1]/zs+K[i][1,2]).astype(int)
        ok&=(ui>=0)&(ui<W)&(vi>=0)&(vi<H)
        uc=np.clip(ui,0,W-1); vc=np.clip(vi,0,H-1)
        ok&=Mk[i][vc,uc]&(D[i][vc,uc]>1e-6)
        if ok.sum()<200: continue
        r=np.abs(zz[ok]-D[i][vc,uc][ok])/D[i][vc,uc][ok]; r=r[r<0.5]
        if r.size>200: rel.append(np.median(r))
    return np.median(rel),len(rel)
base=M.sum()
cv=C[M]
print(f"{'官方percentile':>14} {'置信阈':>7} {'保留':>7} {'重影中位':>9}")
for q in (10,30,50,70,80,90):
    th=np.percentile(cv,q); Mk=M&(C>=th)
    g,np_=ghost(Mk)
    print(f"{q:>14} {th:>7.3f} {100*Mk.sum()/base:>6.1f}% {g*100:>8.2f}%",flush=True)
