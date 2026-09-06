# 精确剪枝率探针(只计数,不改结果):fx13 真实 u8 描述子,行/列 oracle second 阈值,前缀 K 维部分和 + 整数 Cauchy–Schwarz 剩余界。
import numpy as np, sys, time, math
d='/Users/kaidongwang/Developer/pw_android_probe/fx13/'
A=np.fromfile(d+'a.u8',dtype=np.uint8).reshape(-1,128).astype(np.int32); B=np.fromfile(d+'b.u8',dtype=np.uint8).reshape(-1,128).astype(np.int32)
nA,nB=len(A),len(B); print('nA',nA,'nB',nB,'zeros A %.1f%% B %.1f%%'%(100*(A==0).mean(),100*(B==0).mean()), 'normA mean %.1f'%np.sqrt((A*A).sum(1)).mean(), flush=True)
t0=time.time()
# 全量点积(分块),得每行/每列 best 与 second(整数)
BT=B.T.astype(np.int32)
rowBest=np.zeros(nA,np.int32); rowSec=np.zeros(nA,np.int32); colBest=np.zeros(nB,np.int32); colSec=np.zeros(nB,np.int32)
blk=512
for i in range(0,nA,blk):
    D=A[i:i+blk]@BT
    p=np.partition(D,-2,axis=1); rowBest[i:i+blk]=p[:,-1]; rowSec[i:i+blk]=p[:,-2]
    # 列向:逐块更新 colBest/colSec(保持 top-2 值语义:second 含重复 best)
    q=np.partition(D,-2,axis=0); b1=q[-1]; b2=q[-2]
    nb=np.maximum(colBest,b1); ns=np.maximum(np.minimum(colBest,b1),np.maximum(colSec,b2)); colBest=nb; colSec=ns
print('full dots done %.1fs'%(time.time()-t0), 'rowSec median',int(np.median(rowSec)),'rowBest median',int(np.median(rowBest)), flush=True)
def isqrt_ceil(x):
    r=np.floor(np.sqrt(x.astype(np.float64))).astype(np.int64); r=np.where(r*r<x,r+1,r); return r
def probe(perm,K,tag):
    Ap=A[:,perm]; Bp=B[:,perm]
    sqA=(Ap[:,K:]**2).sum(1); sqB=(Bp[:,K:]**2).sum(1); urA=isqrt_ceil(sqA); urB=isqrt_ceil(sqB)
    l1A=np.abs(Ap[:,K:]).sum(1); mxA=Ap[:,K:].max(1); l1B=np.abs(Bp[:,K:]).sum(1); mxB=Bp[:,K:].max(1)
    BTp=Bp[:,:K].T
    cnt=dict(pairs=0,pr=0,pc=0,pb=0,tile16=0,g512=0,tiles=0,groups=0)
    hist=np.zeros(16,np.int64)
    for i in range(0,nA,blk):
        Dp=Ap[i:i+blk,:K]@BTp
        ub_cs=Dp+np.outer(urA[i:i+blk],urB)
        ub_h=Dp+np.minimum(np.outer(l1A[i:i+blk],mxB),np.outer(mxA[i:i+blk],l1B))
        UB=np.minimum(ub_cs,ub_h)
        pr=UB<rowSec[i:i+blk,None]; pc=UB<colSec[None,:]; pb=pr&pc
        cnt['pairs']+=pb.size; cnt['pr']+=pr.sum(); cnt['pc']+=pc.sum(); cnt['pb']+=pb.sum()
        # 4x4 tile 全剪 / 512 对(32 行×16 列,近似一个 SIMD 组 × 4x4)全剪
        r,c=pb.shape; r4=r//4*4; c16=c//16*16
        t=pb[:r4,:c16].reshape(r4//4,4,c16//4,4).all(axis=(1,3)); cnt['tile16']+=t.sum(); cnt['tiles']+=t.size
        r32=r//32*32; g=pb[:r32,:c16].reshape(r32//32,32,c16//16,16).all(axis=(1,3)); cnt['g512']+=g.sum(); cnt['groups']+=g.size
        h=np.clip(((UB-rowSec[i:i+blk,None]).astype(np.float64)/262144.0+1.0)*8,0,15).astype(np.int64); hist+=np.bincount(h.ravel(),minlength=16)
    print('%s K=%d: pr %.2f%% pc %.2f%% pb %.2f%% | tile16 %.2f%% g512 %.2f%% | (UB-secR)/N2 hist(-1..+1 step .125): %s'%(tag,K,100*cnt['pr']/cnt['pairs'],100*cnt['pc']/cnt['pairs'],100*cnt['pb']/cnt['pairs'],100*cnt['tile16']/cnt['tiles'],100*cnt['g512']/cnt['groups'],' '.join('%.0f'%(100*x/hist.sum()) for x in hist)), flush=True)
ident=np.arange(128); energy=np.argsort(-((A*A).sum(0)+(B*B).sum(0)))
for K in (32,64,96):
    probe(ident,K,'identity'); probe(energy,K,'energy-sorted')
# PCA 旋转前缀(浮点过滤器,理想界,不含舍入项——只看上限)
X=np.vstack([A,B]).astype(np.float64); mu=X.mean(0); U,s,Vt=np.linalg.svd(X-mu,full_matrices=False)
print('PCA energy cum (first 32/64/96): %.3f %.3f %.3f'%tuple((s[:k]**2).sum()/(s**2).sum() for k in (32,64,96)), flush=True)
Ar=(A-mu)@Vt.T; Br=(B-mu)@Vt.T   # dot(a,b) = dot(Ar,Br) + mu·(a+b) - mu·mu ;对 a,b 固定的常数项不影响比较?——影响:阈值是原 dot,所以用 dot(a,b)=dot(Ar,Br)+mu·a+mu·b-|mu|^2
ma=A@mu; mb=B@mu; mm=mu@mu
for K in (32,64):
    sqA=(Ar[:,K:]**2).sum(1); sqB=(Br[:,K:]**2).sum(1); nrA=np.sqrt(sqA); nrB=np.sqrt(sqB)
    cnt=[0,0,0,0,0,0]
    for i in range(0,nA,blk):
        Dp=Ar[i:i+blk,:K]@Br[:,:K].T
        UB=Dp+np.outer(nrA[i:i+blk],nrB)+ma[i:i+blk,None]+mb[None,:]-mm+1.0   # +1 保守
        pr=UB<rowSec[i:i+blk,None]; pc=UB<colSec[None,:]; pb=pr&pc
        cnt[0]+=pb.size; cnt[1]+=pr.sum(); cnt[2]+=pb.sum()
        r,c=pb.shape; r32=r//32*32; c16=c//16*16; g=pb[:r32,:c16].reshape(r32//32,32,c16//16,16).all(axis=(1,3)); cnt[3]+=g.sum(); cnt[4]+=g.size
    print('PCA-rotated K=%d: pr %.2f%% pb %.2f%% g512 %.2f%%'%(K,100*cnt[1]/cnt[0],100*cnt[2]/cnt[0],100*cnt[3]/cnt[4]), flush=True)
print('PROBE_DONE %.1fs'%(time.time()-t0))
