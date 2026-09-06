# 剪枝探针 v2:PCA 旋转前缀 + 严格上界(含 f16 量化误差项),阈值来源:oracle / 子集预扫(5%,10%)/ 顺序累积;粒度 512 对(32 行×16 列)。
import numpy as np, time
d='/Users/kaidongwang/Developer/pw_android_probe/fx13/'
A=np.fromfile(d+'a.u8',dtype=np.uint8).reshape(-1,128).astype(np.int64); B=np.fromfile(d+'b.u8',dtype=np.uint8).reshape(-1,128).astype(np.int64)
nA,nB=len(A),len(B); t0=time.time(); blk=512; rng=np.random.default_rng(7)
BT=B.T
rowSec=np.zeros(nA,np.int64); rowBest=np.zeros(nA,np.int64); colBest=np.zeros(nB,np.int64); colSec=np.zeros(nB,np.int64)
for i in range(0,nA,blk):
    D=A[i:i+blk]@BT; p=np.partition(D,-2,axis=1); rowBest[i:i+blk]=p[:,-1]; rowSec[i:i+blk]=p[:,-2]
    q=np.partition(D,-2,axis=0); b1=q[-1]; b2=q[-2]; nb=np.maximum(colBest,b1); ns=np.maximum(np.minimum(colBest,b1),np.maximum(colSec,b2)); colBest=nb; colSec=ns
print('oracle done %.1fs'%(time.time()-t0),flush=True)
# 子集阈值:行阈值 = 对 B 的随机 f 子集算精确点积取 second;列阈值 = 对 A 的随机 f 子集
def subset_thresholds(f):
    jb=np.sort(rng.choice(nB,int(nB*f),replace=False)); ia=np.sort(rng.choice(nA,int(nA*f),replace=False))
    rs=np.zeros(nA,np.int64); cs=np.zeros(nB,np.int64)
    for i in range(0,nA,blk):
        D=A[i:i+blk]@B[jb].T; p=np.partition(D,-2,axis=1); rs[i:i+blk]=p[:,-2]
    D=A[ia]@BT; q=np.partition(D,-2,axis=0); cs[:]=q[-2]
    return rs,cs
# PCA 旋转
X=np.vstack([A,B]).astype(np.float64); mu=X.mean(0); U,s,Vt=np.linalg.svd(X-mu,full_matrices=False)
Ar=(A-mu)@Vt.T; Br=(B-mu)@Vt.T; ma=A@mu; mb=B@mu; mm=mu@mu
def run(K, f16, thr_name, rs, cs):
    # 存储 f16:量化 Ar/Br 前 K 维;误差项:|dot(Ar_pre,Br_pre) - dot(q(Ar),q(Br))| ≤ ‖Ar_pre‖·‖δb‖ + ‖δa‖·‖Br_pre‖ + ‖δa‖‖δb‖(δ = 量化误差向量,取每向量的严格上界)
    Ap=Ar[:,:K]; Bp=Br[:,:K]
    if f16:
        Aq=Ap.astype(np.float16).astype(np.float64); Bq=Bp.astype(np.float16).astype(np.float64)
        da=np.sqrt(((Ap-Aq)**2).sum(1)); db=np.sqrt(((Bp-Bq)**2).sum(1)); na=np.sqrt((Ap**2).sum(1)); nbn=np.sqrt((Bp**2).sum(1))
    else:
        Aq,Bq=Ap,Bp; da=np.zeros(nA); db=np.zeros(nB); na=np.sqrt((Ap**2).sum(1)); nbn=np.sqrt((Bp**2).sum(1))
    ra=np.sqrt((Ar[:,K:]**2).sum(1)); rb=np.sqrt((Br[:,K:]**2).sum(1))
    cnt=[0,0,0,0,0]
    for i in range(0,nA,blk):
        Dq=Aq[i:i+blk]@Bq.T
        err=np.outer(na[i:i+blk],db)+np.outer(da[i:i+blk],nbn)+np.outer(da[i:i+blk],db)
        UB=Dq+err+np.outer(ra[i:i+blk],rb)+ma[i:i+blk,None]+mb[None,:]-mm+2.0   # +2 覆盖 f32 累加舍入(64 项 ≤ 1 ULP 级)
        pb=(UB<rs[i:i+blk,None])&(UB<cs[None,:])
        cnt[0]+=pb.size; cnt[1]+=pb.sum(); r,c=pb.shape; r32=r//32*32; c16=c//16*16
        g=pb[:r32,:c16].reshape(r32//32,32,c16//16,16).all(axis=(1,3)); cnt[2]+=g.sum(); cnt[3]+=g.size
    g512=cnt[2]/cnt[3]; cost=K/128+(1-g512)*1.0
    print('K=%d f16=%d thr=%-9s: pairs %.2f%%  g512 %.2f%%  est_cost=%.2f (prefix %.2f + survivors %.2f)'%(K,f16,thr_name,100*cnt[1]/cnt[0],100*g512,cost,K/128,1-g512),flush=True)
for K in (32,64):
    run(K,False,'oracle',rowSec,colSec); run(K,True,'oracle',rowSec,colSec)
for f in (0.05,0.10):
    rs,cs=subset_thresholds(f); print('subset %.0f%%: rowThr/rowSec median ratio %.3f colThr/colSec %.3f'%(100*f,np.median(rs/np.maximum(rowSec,1)),np.median(cs/np.maximum(colSec,1))),flush=True)
    for K in (32,64): run(K,True,'sub%d'%int(100*f),rs,cs)
# 顺序阈值(行:按列 tile 顺序累积精确 second;列:只用本 WG 的 32 行累积)——保守近似:行阈值取"前 t 个 tile 的精确 second",列阈值取本行块内的
print('sequential thresholds: simulated per 32-row block, tiles of 16 cols in order',flush=True)
K=64; Aq=Ar[:,:K].astype(np.float16).astype(np.float64); Bq=Br[:,:K].astype(np.float16).astype(np.float64)
da=np.sqrt(((Ar[:,:K]-Aq)**2).sum(1)); db=np.sqrt(((Br[:,:K]-Bq)**2).sum(1)); na=np.sqrt((Ar[:,:K]**2).sum(1)); nbn=np.sqrt((Br[:,:K]**2).sum(1)); ra=np.sqrt((Ar[:,K:]**2).sum(1)); rb=np.sqrt((Br[:,K:]**2).sum(1))
tot=0; skip=0
for i in range(0,nA,32):
    a=A[i:i+32]; Dfull=a@BT   # 精确点积(只在"幸存"处才会被真算,这里用于取阈值)
    Dq=Aq[i:i+32]@Bq.T; err=np.outer(na[i:i+32],db)+np.outer(da[i:i+32],nbn)+np.outer(da[i:i+32],db); UB=Dq+err+np.outer(ra[i:i+32],rb)+ma[i:i+32,None]+mb[None,:]-mm+2.0
    rb1=np.zeros(32,np.int64); rb2=np.zeros(32,np.int64)
    for j in range(0,nB,16):
        cthr=np.zeros(16,np.int64)  # 列阈值:本块内还没看过其他行 ⇒ 0(最保守)
        g=(UB[:,j:j+16]<rb2[:,None]).all() and (UB[:,j:j+16]<cthr[None,:]).all()
        tot+=1
        if g: skip+=1; continue
        Dt=Dfull[:,j:j+16]; p=np.sort(Dt,axis=1); b1=p[:,-1]; b2=p[:,-2]
        nb1=np.maximum(rb1,b1); rb2=np.maximum(np.minimum(rb1,b1),np.maximum(rb2,b2)); rb1=nb1
print('sequential (row-only thresholds, col thr=0): g512 skip %.2f%%'%(100*skip/tot),flush=True)
print('PROBE2_DONE %.1fs'%(time.time()-t0))
