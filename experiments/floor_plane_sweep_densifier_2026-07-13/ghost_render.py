import numpy as np
from PIL import Image
d=np.load('xsec_data.npz')
pu,pfd=d['prod_u'],d['prod_fd']; su,sfd=d['ps_u'],d['ps_fd']
# near-floor slab only
m=np.abs(pfd)<60; pu,pfd=pu[m],pfd[m]
umin,umax=min(pu.min(),su.min()),max(pu.max(),su.max())
FMIN,FMAX=-60,60
W=1500; H=560
def px(u,fd):
    x=((u-umin)/(umax-umin)*(W-40)+20).astype(int)
    y=((FMAX-fd)/(FMAX-FMIN)*(H-80)+40).astype(int)
    return x,y
def panel(u,fd,col,title,ghost=True):
    c=np.full((H,W,3),20,np.uint8)
    # floor=0 line
    _,y0=px(np.array([0]),np.array([0])); y0=y0[0]
    c[y0-1:y0+1,20:W-20]=(60,60,60)
    # ghost band shade -35..-15
    _,yg1=px(np.array([0]),np.array([-15])); _,yg2=px(np.array([0]),np.array([-35]))
    if ghost: c[yg1[0]:yg2[0],20:W-20]=(45,25,25)
    x,y=px(u,fd)
    ok=(x>=0)&(x<W)&(y>=0)&(y<H); 
    for xi,yi,ci in zip(x[ok],y[ok],(col if col.ndim>1 else np.tile(col,(ok.sum(),1)))):
        c[max(0,yi-1):yi+2,max(0,xi-1):xi+2]=ci
    return c
gray=np.array([180,175,170]); grn=np.array([90,220,120])
A=panel(pu,pfd,gray,'prod')
B=panel(su,sfd,grn,'ps',ghost=False)
gap=np.full((24,W,3),40,np.uint8)
img=np.concatenate([A,gap,B],0)
Image.fromarray(img).save('ghost_crosssection.png')
print("saved ghost_crosssection.png  (上=老三角化,横截面; 下=plane-sweep)")
print("上图: floor_dist -60~+60mm, 0线灰, 鬼层带-15~-35暗红底; 能看到地板下第二层散点")
print("下图: plane-sweep 全贴0线, 无地板下散点")
