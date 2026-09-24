#!/usr/bin/env python3
"""把 texrecon 的 309 张贴图按每个顶点的 (material, uv) 采样成顶点色, 输出判决页 bins。
只为肉眼对照用: 顶点间距 ~2.7mm, 比贴图粗, 但足以看出接缝/色块/一致性。
帧: texrecon 的 obj 与 C_filt/mesh_aligned.obj 同帧(SfM 帧), 展示帧要取负 y,z(与 obj2meshbins 一致)。"""
import os, re, sys, json, time, numpy as np
os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
import cv2
OBJ='/root/texrecon_out/poisson.obj'; TEXDIR='/root/texrecon_out'; OUT='/root/page_adc/bin'; TAG='mesh_T_texrecon'
CH_TRI=40_000_000; t0=time.time()
V=[];VT=[];F=[];FM=[];cur=-1;mat_order=[];mat_id={}
for ln in open(OBJ, errors='ignore'):
    if ln.startswith('v '): V.append(ln[2:])
    elif ln.startswith('vt '): VT.append(ln[3:])
    elif ln.startswith('usemtl'):
        nm=ln.split()[1]
        if nm not in mat_id: mat_id[nm]=len(mat_order); mat_order.append(nm)
        cur=mat_id[nm]
    elif ln.startswith('f '): F.append(ln[2:]); FM.append(cur)
V=np.fromstring(''.join(V),sep=' ',dtype=np.float64).reshape(-1,3)
VT=np.fromstring(''.join(VT),sep=' ',dtype=np.float32).reshape(-1,2)
nc=F[0].split()[0].count('/')+1
Fi=np.fromstring(''.join(F).replace('/',' '),sep=' ',dtype=np.int64).reshape(-1,3,nc)
FM=np.asarray(FM,np.int64)
print(f'obj: {len(V):,} v  {len(VT):,} vt  {len(Fi):,} f  {len(mat_order)} 材质  ({time.time()-t0:.0f}s)',flush=True)
vi=Fi[:,:,0]-1; ti=Fi[:,:,1]-1
COL=np.zeros((len(V),3),np.uint8); GOT=np.zeros(len(V),bool)
for mi,nm in enumerate(mat_order):
    sel=FM==mi
    if not sel.any(): continue
    img=cv2.imread(f'{TEXDIR}/poisson_{nm}_map_Kd.png',cv2.IMREAD_COLOR)
    if img is None: continue
    h,w=img.shape[:2]
    vv=vi[sel].ravel(); tt=ti[sel].ravel()
    u=np.clip((VT[tt,0]*w).astype(np.int32),0,w-1)
    y=np.clip(((1.0-VT[tt,1])*h).astype(np.int32),0,h-1)
    c=img[y,u][:,::-1]
    new=~GOT[vv]
    COL[vv[new]]=c[new]; GOT[vv[new]]=True
    if mi%60==0: print(f'  材质 {mi}/{len(mat_order)}  已着色 {GOT.sum():,}/{len(V):,}  ({time.time()-t0:.0f}s)',flush=True)
print(f'着色完成 {GOT.sum():,}/{len(V):,} ({100*GOT.mean():.1f}%)  未命中的留黑  ({time.time()-t0:.0f}s)')
a,b,c3=V[Fi[:,0,0]-1],V[Fi[:,1,0]-1],V[Fi[:,2,0]-1]
fn=np.cross(b-a,c3-a); N=np.zeros_like(V)
for k in range(3): np.add.at(N,Fi[:,k,0]-1,fn)
n=np.linalg.norm(N,axis=1,keepdims=True); n[n==0]=1; N=(N/n).astype(np.float32)
Vf=V.astype(np.float32); Vf[:,1]*=-1; Vf[:,2]*=-1; N[:,1]*=-1; N[:,2]*=-1
N8=np.clip(np.round(N*127),-127,127).astype(np.int8)
Vf.tofile(f'{OUT}/{TAG}.pos'); COL.tofile(f'{OUT}/{TAG}.col'); N8.tofile(f'{OUT}/{TAG}.nrm')
T=(Fi[:,:,0]-1).astype(np.uint32); np_=(len(T)+CH_TRI-1)//CH_TRI
for k,off in enumerate(range(0,len(T),CH_TRI)):
    T[off:off+CH_TRI].astype('<u4').tofile(f'{OUT}/{TAG}.idx'+('' if np_==1 else f'.{k}'))
lo=np.percentile(Vf,1,0); hi=np.percentile(Vf,99,0); med=np.median(Vf,0)
rad=float(np.percentile(np.linalg.norm(Vf-med,axis=1),95))
mp=f'{OUT}/meta.json'; meta=json.load(open(mp)) if os.path.exists(mp) else {}
meta[TAG]={'kind':'mesh','n':int(len(Vf)),'tris':int(len(T)),'center':((lo+hi)/2).tolist(),
           'ext':(hi-lo).tolist(),'med':med.astype(float).tolist(),'radius':rad,'idx_parts':int(np_)}
json.dump(meta,open(mp,'w'),ensure_ascii=False,indent=1)
print(f'done {TAG}: {len(Vf):,} v / {len(T):,} tris  展示帧中位 {np.round(med,3).tolist()} radius {rad:.3f}  ({time.time()-t0:.0f}s)')
