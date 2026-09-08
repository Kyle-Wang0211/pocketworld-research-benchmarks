import numpy as np, sys, itertools
W,H=int(sys.argv[1]),int(sys.argv[2]); img=np.fromfile(sys.argv[3],np.uint8).reshape(H,W)
ref=np.fromfile(sys.argv[4],np.uint8).reshape(H,W)
gp=np.fromfile(sys.argv[5],np.uint8).reshape(H+42,W+42)[21:21+H,21:21+W]
print("gpu vs cpu401 mismatches:", int((gp!=ref).sum()))
tw,th=W//8,H//8; total=tw*th; lutScale=np.float32(255.0)/np.float32(total); clip=max(int(6.0*total/256),1)
def rnd(x,mode): return np.rint(x) if mode=='even' else np.floor(np.abs(x)+0.5)*np.sign(x)
def build_lut(mode):
  lut=np.zeros((8,8,256),np.float32)
  for ty in range(8):
    for tx in range(8):
      h=np.bincount(img[ty*th:(ty+1)*th,tx*tw:(tx+1)*tw].ravel(),minlength=256).astype(np.int64)
      clipped=int(np.maximum(h-clip,0).sum()); h=np.minimum(h,clip); rb=clipped//256; res=clipped-rb*256; h=h+rb
      if res:
        step=max(256//res,1); i=0
        while i<256 and res>0: h[i]+=1; i+=step; res-=1
      s=np.cumsum(h).astype(np.float32); lut[ty,tx]=np.clip(rnd(s*lutScale,mode),0,255)
  return lut
def coords(n,t,inv):
  f=np.arange(n,dtype=np.float32)*inv-np.float32(0.5); i1=np.floor(f).astype(np.int32); a=(f-i1.astype(np.float32)).astype(np.float32); a1=np.float32(1)-a
  return np.maximum(i1,0),np.minimum(i1+1,t-1),a,a1
tx1,tx2,xa,xa1=coords(W,8,np.float32(1)/np.float32(tw)); ty1,ty2,ya,ya1=coords(H,8,np.float32(1)/np.float32(th))
XA=xa[None,:]; XA1=xa1[None,:]; YA=ya[:,None]; YA1=ya1[:,None]
f32=lambda x:x.astype(np.float32)
def fma(a,b,c): return f32(a.astype(np.float64)*b.astype(np.float64)+c.astype(np.float64))
def mul_add(a,b,c,d,mode):  # a*b + c*d
  if mode==0: return f32(f32(a*b)+f32(c*d))
  if mode==1: return fma(c,d,f32(a*b))   # contract second
  if mode==2: return fma(a,b,f32(c*d))   # contract first
best=None
for lm in ('even','away'):
  lut=build_lut(lm)
  L1a=lut[ty1[:,None],tx1[None,:],img]; L1b=lut[ty1[:,None],tx2[None,:],img]; L2a=lut[ty2[:,None],tx1[None,:],img]; L2b=lut[ty2[:,None],tx2[None,:],img]
  for m1,m2,m3,im in itertools.product((0,1,2),(0,1,2),(0,1,2),('even','away')):
    t1=mul_add(L1a,XA1,L1b,XA,m1); t2=mul_add(L2a,XA1,L2b,XA,m2); r=mul_add(t1,YA1,t2,YA,m3)
    out=np.clip(rnd(r,im),0,255).astype(np.uint8); n=int((out!=gp).sum())
    if best is None or n<best[0]: best=(n,lm,m1,m2,m3,im)
    if n==0: print("EXACT variant: lut_round=%s inner=%d/%d outer=%d interp_round=%s"%(lm,m1,m2,m3,im))
print("best:",best)
