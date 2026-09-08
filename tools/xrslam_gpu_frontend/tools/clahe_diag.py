import numpy as np, sys
W,H=int(sys.argv[1]),int(sys.argv[2]); img=np.fromfile(sys.argv[3],np.uint8).reshape(H,W)
refs={k:np.fromfile(v,np.uint8).reshape(H,W) for k,v in (a.split('=') for a in sys.argv[4:])}
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
def coords(n,t,inv):
  f=np.arange(n,dtype=np.float32)*inv-np.float32(0.5); i1=np.floor(f).astype(np.int32); a=(f-i1.astype(np.float32)).astype(np.float32); a1=np.float32(1)-a
  return np.maximum(i1,0),np.minimum(i1+1,t-1),a,a1
tx1,tx2,xa,xa1=coords(W,8,np.float32(1)/np.float32(tw)); ty1,ty2,ya,ya1=coords(H,8,np.float32(1)/np.float32(th))
L1a=lut[ty1[:,None],tx1[None,:],img]; L1b=lut[ty1[:,None],tx2[None,:],img]; L2a=lut[ty2[:,None],tx1[None,:],img]; L2b=lut[ty2[:,None],tx2[None,:],img]
XA=xa[None,:]; XA1=xa1[None,:]; YA=ya[:,None]; YA1=ya1[:,None]
def f32(x): return x.astype(np.float32)
def fma(a,b,c): return f32(a.astype(np.float64)*b.astype(np.float64)+c.astype(np.float64))
plain=f32(f32(f32(L1a*XA1)+f32(L1b*XA))*YA1+f32(f32(L2a*XA1)+f32(L2b*XA))*YA)
t1=fma(L1b,XA,f32(L1a*XA1)); t2=fma(L2b,XA,f32(L2a*XA1)); fmav=fma(t2,YA,f32(t1*YA1))
out={'plain':np.clip(np.rint(plain),0,255).astype(np.uint8),'fma':np.clip(np.rint(fmav),0,255).astype(np.uint8)}
for rn,r in refs.items():
  for vn,v in out.items():
    d=(v!=r); print(f"{rn:12s} vs {vn:5s}: mismatches={int(d.sum())} maxdiff={int(np.abs(v.astype(int)-r.astype(int)).max())}")
d=(out['plain']!=refs[list(refs)[0]]); ys,xs=np.nonzero(d)
for y,x in list(zip(ys,xs))[:3]: print(f"  ({x},{y}) img={img[y,x]} ref={refs[list(refs)[0]][y,x]} plain={plain[y,x]:.6f} fma={fmav[y,x]:.6f}")
