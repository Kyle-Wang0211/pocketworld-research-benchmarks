import numpy as np, sys
W,H=int(sys.argv[1]),int(sys.argv[2]); d=sys.argv[3]; img=np.fromfile(sys.argv[4],np.uint8).reshape(H,W)
ref=np.fromfile(d+'/next_clahe.u8',np.uint8).reshape(H,W); glut=np.fromfile(d+'/gpu_lut.u32',np.uint32).reshape(8,8,256); gres=np.fromfile(d+'/gpu_res.f32',np.float32).reshape(H,W)
tw,th=W//8,H//8; total=tw*th; lutScale=np.float32(255.0)/np.float32(total); clip=max(int(6.0*total/256),1)
lut=np.zeros((8,8,256),np.float32)
for ty in range(8):
  for tx in range(8):
    h=np.bincount(img[ty*th:(ty+1)*th,tx*tw:(tx+1)*tw].ravel(),minlength=256).astype(np.int64)
    clipped=int(np.maximum(h-clip,0).sum()); h=np.minimum(h,clip); rb=clipped//256; res=clipped-rb*256; h=h+rb
    if res:
      step=max(256//res,1); i=0
      while i<256 and res>0: h[i]+=1; i+=step; res-=1
    s=np.cumsum(h).astype(np.float32); lut[ty,tx]=np.clip(np.rint(s*lutScale),0,255)
print("LUT mismatches gpu vs cpu-replica:", int((glut!=lut.astype(np.uint32)).sum()), "of", lut.size)
mm=np.argwhere(glut!=lut.astype(np.uint32))
for ty,tx,i in mm[:4]:
  h=np.bincount(img[ty*th:(ty+1)*th,tx*tw:(tx+1)*tw].ravel(),minlength=256).astype(np.int64)
  clipped=int(np.maximum(h-clip,0).sum()); h=np.minimum(h,clip); rb=clipped//256; res=clipped-rb*256; h=h+rb
  if res:
    step=max(256//res,1); k=0
    while k<256 and res>0: h[k]+=1; k+=step; res-=1
  s_=np.cumsum(h).astype(np.float32); print(f"  tile({tx},{ty}) bin {i}: sum={int(s_[i])} sum*scale={np.float32(s_[i]*lutScale)!r} cpu={int(lut[ty,tx,i])} gpu={int(glut[ty,tx,i])}")
f32=lambda x:x.astype(np.float32)
def coords(n,t,inv,fuse):
  x=np.arange(n,dtype=np.float32)
  f=f32(x.astype(np.float64)*np.float64(inv)-0.5) if fuse else f32(f32(x*inv)-np.float32(0.5))
  i1=np.floor(f).astype(np.int32); a=f32(f-i1.astype(np.float32)); a1=f32(np.float32(1)-a)
  return np.maximum(i1,0),np.minimum(i1+1,t-1),a,a1
def fma(a,b,c): return f32(a.astype(np.float64)*b.astype(np.float64)+c.astype(np.float64))
def interp(fusex,fusey,m):
  tx1,tx2,xa,xa1=coords(W,8,np.float32(1)/np.float32(tw),fusex); ty1,ty2,ya,ya1=coords(H,8,np.float32(1)/np.float32(th),fusey)
  XA=xa[None,:]; XA1=xa1[None,:]; YA=ya[:,None]; YA1=ya1[:,None]
  L1a=lut[ty1[:,None],tx1[None,:],img]; L1b=lut[ty1[:,None],tx2[None,:],img]; L2a=lut[ty2[:,None],tx1[None,:],img]; L2b=lut[ty2[:,None],tx2[None,:],img]
  def ma(a,b,c,dd,mode):
    if mode==0: return f32(f32(a*b)+f32(c*dd))
    if mode==1: return fma(c,dd,f32(a*b))
    return fma(a,b,f32(c*dd))
  t1=ma(L1a,XA1,L1b,XA,m[0]); t2=ma(L2a,XA1,L2b,XA,m[1]); return ma(t1,YA1,t2,YA,m[2])
import itertools
best=None
for fx,fy,m in itertools.product((0,1),(0,1),itertools.product((0,1,2),repeat=3)):
  r=interp(fx,fy,m); n=int((r!=gres).sum())
  if best is None or n<best[0]: best=(n,fx,fy,m)
  if n==0: print("EXACT res variant: fuse_txf=%d fuse_tyf=%d contraction=%s"%(fx,fy,m))
print("best res variant:",best)
r=interp(0,0,(0,0,0)); dd=(r!=gres); ys,xs=np.nonzero(dd); print("plain res != gpu res at", int(dd.sum()), "px")
for y,x in list(zip(ys,xs))[:4]:
  print(f"  ({x},{y}) v={img[y,x]} cpu_res={r[y,x]!r} gpu_res={gres[y,x]!r} diff={float(gres[y,x])-float(r[y,x]):.3e}")
