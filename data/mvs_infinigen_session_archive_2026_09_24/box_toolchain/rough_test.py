import numpy as np, json, glob, os, OpenEXR, time
t0=time.time(); ST=4
d=json.load(open('/root/av_ep0_off/scene_dense.sfm'))
I=d['intrinsics'][0]; W0=int(I['width']); H0=int(I['height'])
f=float(I['focalLength'])/float(I['sensorWidth'])*W0; pp=[float(x) for x in I['principalPoint']]
poses={p['poseId']:p['pose']['transform'] for p in d['poses']}
views=sorted([v for v in d['views'] if v['poseId'] in poses], key=lambda v:v['path'])
vid2idx={v['viewId']:i for i,v in enumerate(views)}; NC=len(views)
KI=[None]*NC; CC=np.zeros((NC,3)); RR=[None]*NC; PATH=[None]*NC
P=[]; SRC=[]; PU=[]; PV=[]
for dp in sorted(glob.glob('/root/av_ep0_off/filt/*_depthMap.exr')):
    vid=os.path.basename(dp).split('_')[0]
    if vid not in vid2idx: continue
    i=vid2idx[vid]; PATH[i]=dp
    with OpenEXR.File(dp) as fh:
        h=dict(fh.header()); Z=np.asarray(fh.channels()['Y'].pixels,dtype=np.float32)
    KI[i]=np.asarray(h['AliceVision:iCamArr'],dtype=np.float64).reshape(3,3)
    CC[i]=np.asarray(h['AliceVision:CArr'],dtype=np.float64).reshape(3)
    t=poses[views[i]['poseId']]; RR[i]=np.array([float(x) for x in t['rotation']]).reshape(3,3)
    Zs=Z[::ST,::ST]; hh,ww=Zs.shape
    u,v=np.meshgrid(np.arange(ww)*ST,np.arange(hh)*ST); ok=Zs>0
    if ok.any():
        dd=np.stack([u[ok],v[ok],np.ones(int(ok.sum()))],1)@KI[i].T; dd/=np.linalg.norm(dd,axis=1,keepdims=True)
        P.append((CC[i]+dd*Zs[ok][:,None]).astype(np.float32)); SRC.append(np.full(int(ok.sum()),i,np.int16))
        PU.append(u[ok].astype(np.int32)); PV.append(v[ok].astype(np.int32))
P=np.concatenate(P); SRC=np.concatenate(SRC); PU=np.concatenate(PU); PV=np.concatenate(PV)
SW,SH=336,250; sca=W0/SW; fx=f/sca; cx=(W0/2+pp[0])/sca; cy=(H0/2+pp[1])/sca
lab=np.zeros(len(P),np.int8); idxall=np.arange(len(P))
for kk in [0,33,66,99]:
    R=RR[kk]; C=CC[kk]
    X=(P-C)@R.T; z=X[:,2]; m0=z>1e-6; gi=idxall[m0]
    u=(X[m0,0]/z[m0]*fx+cx); v=(X[m0,1]/z[m0]*fx+cy); zz=z[m0]
    iu=np.floor(u).astype(np.int32); iv=np.floor(v).astype(np.int32)
    m=(iu>=0)&(iu<SW)&(iv>=0)&(iv<SH); iu,iv,zz,gi=iu[m],iv[m],zz[m],gi[m]
    pix=iv.astype(np.int64)*SW+iu; o=np.lexsort((zz,pix)); pix=pix[o]; zz=zz[o]; gi=gi[o]
    st=np.r_[0,np.where(np.diff(pix))[0]+1]; en=np.r_[st[1:],len(pix)]
    for s_,e_ in zip(st,en):
        if e_-s_<8: continue
        g=np.diff(zz[s_:e_])
        if not (g>0.02).any(): continue
        j=int(np.argmax(g>0.02)); lab[gi[s_:s_+j+1]]=1; lab[gi[s_+j+1:e_]]=2
print(f'{len(P):,} 点, 近 {(lab==1).sum():,} 远 {(lab==2).sum():,}  ({time.time()-t0:.0f}s)',flush=True)
rough=np.full(len(P),np.nan,np.float32); nscat=np.full(len(P),np.nan,np.float32)
Wn=3
for i in range(NC):
    if PATH[i] is None: continue
    sel=np.where((SRC==i)&(lab>0))[0]
    if len(sel)==0: continue
    with OpenEXR.File(PATH[i]) as fh:
        Z=np.asarray(fh.channels()['Y'].pixels,dtype=np.float32)
    Hd,Wd=Z.shape; iC=KI[i]
    yy,xx=np.mgrid[0:Hd,0:Wd]
    D=np.stack([xx,yy,np.ones_like(xx)],-1).reshape(-1,3).astype(np.float64)@iC.T
    D/=np.linalg.norm(D,axis=1,keepdims=True); D=D.reshape(Hd,Wd,3)
    Pw=(D*Z[...,None]).astype(np.float32)
    gx=np.zeros_like(Pw); gy=np.zeros_like(Pw)
    gx[:,1:-1]=Pw[:,2:]-Pw[:,:-2]; gy[1:-1]=Pw[2:]-Pw[:-2]
    N=np.cross(gx,gy); nl=np.linalg.norm(N,axis=-1); good=(Z>0)&(nl>1e-12)
    N[good]=N[good]/nl[good][:,None]
    for k in sel:
        u0,v0=int(PU[k]),int(PV[k])
        a,b=max(v0-Wn,0),min(v0+Wn+1,Hd); c_,e_=max(u0-Wn,0),min(u0+Wn+1,Wd)
        zb=Z[a:b,c_:e_]; msk=zb>0
        if msk.sum()<12: continue
        pts=Pw[a:b,c_:e_][msk].astype(np.float64)
        mu=pts.mean(0); Q=pts-mu
        try: _,_,vt=np.linalg.svd(Q,full_matrices=False)
        except Exception: continue
        rough[k]=np.abs(Q@vt[2]).mean()/max(float(Z[v0,u0]),1e-6)
        gm=msk&good[a:b,c_:e_]
        nb=N[a:b,c_:e_][gm]
        if len(nb)>=8 and good[v0,u0]:
            n0=N[v0,u0]
            nscat[k]=np.degrees(np.arccos(np.clip(np.abs(nb@n0),0,1))).mean()
A=(lab==1)&~np.isnan(rough); B=(lab==2)&~np.isnan(rough)
print(f'\n=== 局部粗糙度(7x7 平面拟合残差/深度)  近 {A.sum():,} / 远 {B.sum():,}')
for q in [25,50,75,90]:
    ra=np.percentile(rough[A],q); rb=np.percentile(rough[B],q)
    print(f'  p{q:<2}  近 {ra:.5f}  远 {rb:.5f}  比 {rb/max(ra,1e-12):5.2f}x')
An=(lab==1)&~np.isnan(nscat); Bn=(lab==2)&~np.isnan(nscat)
print(f'\n=== 法线散度(本像素 vs 邻域 平均夹角)  近 {An.sum():,} / 远 {Bn.sum():,}')
for q in [25,50,75,90]:
    print(f'  p{q:<2}  近 {np.percentile(nscat[An],q):6.2f}°  远 {np.percentile(nscat[Bn],q):6.2f}°  差 {np.percentile(nscat[Bn],q)-np.percentile(nscat[An],q):+6.2f}°')
print('\n=== 判别力: 按法线散度切(AGS-Mesh 用 10°)')
for th in [5,10,15,20,30,45]:
    ra=(nscat[An]>th).mean(); rb=(nscat[Bn]>th).mean()
    print(f'  散度>{th:<3}°  切近簇 {100*ra:5.2f}%  切远簇 {100*rb:5.2f}%  富集 {rb/max(ra,1e-9):5.2f}x')
print('\n=== 判别力: 按粗糙度切')
for q in [50,70,80,90,95]:
    th=np.percentile(rough[A],q); ra=(rough[A]>th).mean(); rb=(rough[B]>th).mean()
    print(f'  粗糙>近p{q:<2}  切近簇 {100*ra:5.2f}%  切远簇 {100*rb:5.2f}%  富集 {rb/max(ra,1e-9):5.2f}x')
print(f'  ({time.time()-t0:.0f}s)')
