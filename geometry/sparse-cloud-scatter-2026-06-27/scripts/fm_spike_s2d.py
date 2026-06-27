# featuremetric 点+联合位姿 精修 spike (PixSfM 算法自研进 COLMAP 4.0.4)。
# 用法: KMP_DUPLICATE_LIB_OK=TRUE python3.11 fm_spike_s2d.py [MAXEDGE] [NGLOBE] [CAPOBS] [ITERS] [JOINT]
# 环境: macOS python3.11 + torch + pycolmap 4.0.4 + s2dnet_mod.py(同目录)。固定位姿版把 JOINT=0。
import os
os.environ['KMP_DUPLICATE_LIB_OK']='TRUE'; os.environ['OMP_NUM_THREADS']='1'
import sys; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import pycolmap, numpy as np, torch, torch.nn.functional as F, time
from s2dnet_mod import S2DNet
from PIL import Image
np.random.seed(0); torch.manual_seed(0)
DEV='mps' if torch.backends.mps.is_available() else 'cpu'
RECON=os.environ.get('RECON','/tmp/batch_dense')          # COLMAP 4.0.4 重建目录
IMGDIR=os.environ['IMGDIR']                                # 原图目录
CKPT=os.environ.get('S2DNET','s2dnet_weights.pth')
MAXEDGE=int(sys.argv[1]) if len(sys.argv)>1 else 1600
NGLOBE=int(sys.argv[2]) if len(sys.argv)>2 else 8000
CAPOBS=int(sys.argv[3]) if len(sys.argv)>3 else 6
ITERS=int(sys.argv[4]) if len(sys.argv)>4 else 150
JOINT=int(sys.argv[5]) if len(sys.argv)>5 else 1
PATCH=8; HALF=PATCH//2
rec=pycolmap.Reconstruction(RECON); pids=list(rec.points3D.keys()); Np=len(pids)
XYZ=np.array([rec.points3D[p].xyz for p in pids],np.float64)
def fitS(P):
    A=np.c_[2*P,np.ones(len(P))];b=(P**2).sum(1);c,*_=np.linalg.lstsq(A,b,rcond=None);ct=c[:3];return ct,np.sqrt(max(1e-9,c[3]+(ct**2).sum()))
span=np.percentile(np.linalg.norm(XYZ-np.median(XYZ,0),axis=1),90)
sub=XYZ[np.random.choice(Np,min(20000,Np),replace=False)];best=None;bn=0
for _ in range(2000):
    ix=np.random.choice(len(sub),4,replace=False)
    try:cc,rad=fitS(sub[ix])
    except:continue
    if not(span*0.02<rad<span*0.30):continue
    dd=np.abs(np.linalg.norm(sub-cc,axis=1)-rad);s=int((dd<0.06*rad).sum())
    if s>bn:bn=s;best=(cc,rad)
ct,rad=best
for _ in range(4):
    dd=np.abs(np.linalg.norm(XYZ-ct,axis=1)-rad);inl=dd<0.06*rad;ct,rad=fitS(XYZ[inl])
dd=np.abs(np.linalg.norm(XYZ-ct,axis=1)-rad);gidx=np.where(dd<0.08*rad)[0]
if len(gidx)>NGLOBE: gidx=np.random.choice(gidx,NGLOBE,replace=False)
gpid=[pids[i] for i in gidx]; row_of={p:r for r,p in enumerate(gpid)}; M=len(gpid)
xyz0=np.array([rec.points3D[p].xyz for p in gpid],np.float64)
img_ids=set()
for p in gpid:
    for el in rec.points3D[p].track.elements: img_ids.add(el.image_id)
img_list=sorted(img_ids); iid2idx={iid:k for k,iid in enumerate(img_list)}; nimg=len(img_list)
Rinit=np.zeros((nimg,3,3)); tinit=np.zeros((nimg,3))
for iid in img_list:
    cfw=np.array(rec.images[iid].cam_from_world().matrix()); Rinit[iid2idx[iid]]=cfw[:,:3]; tinit[iid2idx[iid]]=cfw[:,3]
img2obs={}
for p in gpid:
    els=rec.points3D[p].track.elements
    if len(els)>CAPOBS: els=[els[i] for i in np.linspace(0,len(els)-1,CAPOBS).astype(int)]
    for el in els:
        kp=np.array(rec.images[el.image_id].points2D[el.point2D_idx].xy)
        img2obs.setdefault(el.image_id,[]).append((row_of[p],kp))
s2d=S2DNet(CKPT).to(DEV)
cam=rec.cameras[list(rec.cameras.keys())[0]]; f0,cx,cy,k1=[float(v) for v in cam.params]  # SIMPLE_RADIAL
P_patch=[];P_row=[];P_img=[];P_x0=[];P_y0=[];P_sc=[]
for iid,obs in img2obs.items():
    im=rec.images[iid]; path=os.path.join(IMGDIR,im.name)
    if not os.path.exists(path): continue
    pil=Image.open(path).convert('RGB');W0,H0=pil.size;sc=MAXEDGE/max(W0,H0)
    Wd,Hd=int(round(W0*sc)),int(round(H0*sc));pil=pil.resize((Wd,Hd))
    x=torch.from_numpy(np.asarray(pil)).permute(2,0,1).float().div(255.)[None].to(DEV)
    desc=s2d(x)[0].cpu()
    for row,kp in obs:
        kc=kp*sc;x0=int(round(kc[0]))-HALF;y0=int(round(kc[1]))-HALF
        if x0<0 or y0<0 or x0+PATCH>Wd or y0+PATCH>Hd: continue
        P_patch.append(desc[:,y0:y0+PATCH,x0:x0+PATCH].clone());P_row.append(row);P_img.append(iid2idx[iid])
        P_x0.append(x0);P_y0.append(y0);P_sc.append(sc)
patch=torch.stack(P_patch);orow=torch.tensor(P_row);oimg=torch.tensor(P_img)
ox0=torch.tensor(P_x0,dtype=torch.float32);oy0=torch.tensor(P_y0,dtype=torch.float32);osc=torch.tensor(P_sc,dtype=torch.float32)
Ri=torch.tensor(Rinit,dtype=torch.float32);ti_=torch.tensor(tinit,dtype=torch.float32)
def expSO3(w):
    th=w.norm(dim=1,keepdim=True).clamp(min=1e-9);k=w/th
    K=torch.zeros(w.shape[0],3,3)
    K[:,0,1]=-k[:,2];K[:,0,2]=k[:,1];K[:,1,0]=k[:,2];K[:,1,2]=-k[:,0];K[:,2,0]=-k[:,1];K[:,2,1]=k[:,0]
    I=torch.eye(3).expand(w.shape[0],3,3); th=th[:,:,None]
    return I+torch.sin(th)*K+(1-torch.cos(th))*(K@K)
xyz_v=torch.tensor(xyz0,dtype=torch.float32,requires_grad=True)
delta=torch.zeros(nimg,3,requires_grad=JOINT==1);tvar=ti_.clone().requires_grad_(JOINT==1)
def sample(xyzv,delta,tvar):
    R=Ri@expSO3(delta) if JOINT else Ri
    Robs=R[oimg];tobs=tvar[oimg]
    xo=xyzv[orow];pc=(Robs@xo.unsqueeze(-1)).squeeze(-1)+tobs
    xn=pc[:,0]/pc[:,2];yn=pc[:,1]/pc[:,2];r2=xn*xn+yn*yn;fac=1+k1*r2
    u=(f0*fac*xn+cx)*osc-ox0;v=(f0*fac*yn+cy)*osc-oy0
    gx=u/(PATCH-1)*2-1;gy=v/(PATCH-1)*2-1
    return F.grid_sample(patch,torch.stack([gx,gy],-1).view(-1,1,1,2),align_corners=True,padding_mode='border')[:,:,0,0]
with torch.no_grad():
    s0=sample(xyz_v,delta,tvar);ref=torch.zeros(M,128);cnt=torch.zeros(M,1)
    ref.index_add_(0,orow,s0);cnt.index_add_(0,orow,torch.ones(len(orow),1));ref=(ref/cnt.clamp(min=1)).detach()
params=[{'params':[xyz_v],'lr':2e-4}]+([{'params':[delta,tvar],'lr':2e-6}] if JOINT else [])
opt=torch.optim.Adam(params)
cauchy=lambda sq: 0.0625*torch.log1p(sq/0.0625)   # Cauchy(0.25)
for it in range(ITERS):
    opt.zero_grad();s=sample(xyz_v,delta,tvar);loss=cauchy(((s-ref[orow])**2).sum(1)).sum();loss.backward();opt.step()
xyzR=xyz_v.detach().numpy().astype(np.float64)
sh=lambda P:100*((np.linalg.norm(P-ct,axis=1)-rad)/rad).std()
print(f'R={rad:.3f} 内点{M} mode={"joint" if JOINT else "fixed"} | loss地板={loss.item()/len(orow):.5f}')
print(f'球壳 前={sh(xyz0):.2f}% 后={sh(xyzR):.2f}% | 点位移={100*np.linalg.norm(xyzR-xyz0,axis=1).mean()/rad:.2f}%R')
if JOINT: print(f'位姿delta={delta.detach().norm(dim=1).mean():.5f}rad t位移={(tvar.detach()-ti_).norm(dim=1).mean():.5f}')
