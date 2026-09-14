import numpy as np, json
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
S=json.load(open("/root/av/_sfm.sfm"))
intr={i["intrinsicId"]:i for i in S["intrinsics"]}
poses={p["poseId"]:p["pose"]["transform"] for p in S["poses"]}
views=[v for v in S["views"] if v["poseId"] in poses]
V =np.fromstring(open("/root/av/tex/_v.txt").read(),  sep=' ').reshape(-1,3)
VT=np.fromstring(open("/root/av/tex/_vt.txt").read(), sep=' ').reshape(-1,2)
F =np.fromstring(open("/root/av/tex/_f.txt").read(),  sep=' ', dtype=np.int64).reshape(-1,6)
rng=np.random.default_rng(0); tri=F[rng.choice(len(F), 6000, replace=False)]
c3 =(V[tri[:,0]-1]+V[tri[:,2]-1]+V[tri[:,4]-1])/3.0
cuv=(VT[tri[:,1]-1]+VT[tri[:,3]-1]+VT[tri[:,5]-1])/3.0
A=np.asarray(Image.open("/root/av/tex/texture_1001.png").convert("RGB"),dtype=np.float32)
H,W,_=A.shape
tex=A[np.clip(((1-cuv[:,1])*H).astype(int),0,H-1), np.clip((cuv[:,0]*W).astype(int),0,W-1)]
X=c3*np.array([1,-1,-1])                      # OBJ -> AliceVision 世界帧
acc=np.zeros((len(X),3,len(views)),np.float32); cnt=np.zeros((len(X),len(views)),bool)
for k,v in enumerate(views):
    T=poses[v["poseId"]]
    R=np.array([float(x) for x in T["rotation"]]).reshape(3,3).T
    C=np.array([float(x) for x in T["center"]])
    I=intr[v["intrinsicId"]]; w=float(I["width"]); h=float(I["height"])
    f=float(I["focalLength"])/float(I["sensorWidth"])*w
    pp=[float(x) for x in I["principalPoint"]]; cx,cy=pp[0]+w/2, pp[1]+h/2
    Xc=(R@(X-C).T).T; z=Xc[:,2]; ok=z>1e-6
    u=f*Xc[:,0]/np.where(ok,z,1)+cx; vv=f*Xc[:,1]/np.where(ok,z,1)+cy
    ok&=(u>=0)&(u<w)&(vv>=0)&(vv<h)
    if not ok.any(): continue
    im=np.asarray(Image.open(v["path"]).convert("RGB"),dtype=np.float32)
    acc[ok,:,k]=im[vv[ok].astype(int),u[ok].astype(int)]; cnt[ok,k]=True
n=cnt.sum(1); good=n>=3
src=np.array([np.median(acc[i][:,cnt[i]],axis=1) for i in np.where(good)[0]])
tx=tex[good]
print(f"配对三角形 {good.sum()} (每个 >=3 视图,取中位色)")
q=[10,25,50,75,90]
def enc(x): x=np.clip(x/255,0,1); return 255*np.where(x<=0.0031308,12.92*x,1.055*x**(1/2.4)-0.055)
print("  分位      ", "  ".join(f"p{x:<3d}" for x in q))
print("  源图取色  ", "  ".join(f"{x:5.1f}" for x in np.percentile(src,q)))
print("  图集      ", "  ".join(f"{x:5.1f}" for x in np.percentile(tx,q)))
print("  图集→sRGB ", "  ".join(f"{x:5.1f}" for x in np.percentile(enc(tx),q)))
g=(src.mean(1)>8)&(tx.mean(1)>2)
print(f"  逐三角形比值 图集/源图  中位 {np.median(tx.mean(1)[g]/src.mean(1)[g]):.3f}")
print(f"  逐三角形比值 sRGB后/源图 中位 {np.median(enc(tx).mean(1)[g]/src.mean(1)[g]):.3f}")
