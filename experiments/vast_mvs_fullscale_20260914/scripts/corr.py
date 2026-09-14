import numpy as np, json
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
S=json.load(open("/root/av/_sfm.sfm"))
intr={i["intrinsicId"]:i for i in S["intrinsics"]}
poses={p["poseId"]:p["pose"]["transform"] for p in S["poses"]}
views=[v for v in S["views"] if v["poseId"] in poses]
print("views with pose:", len(views))
V =np.fromstring(open("/root/av/tex/_v.txt").read(),  sep=' ').reshape(-1,3)
VT=np.fromstring(open("/root/av/tex/_vt.txt").read(), sep=' ').reshape(-1,2)
F =np.fromstring(open("/root/av/tex/_f.txt").read(),  sep=' ', dtype=np.int64).reshape(-1,6)
rng=np.random.default_rng(0); sel=rng.choice(len(F), 4000, replace=False)
tri=F[sel]
c3=(V[tri[:,0]-1]+V[tri[:,2]-1]+V[tri[:,4]-1])/3.0
cuv=(VT[tri[:,1]-1]+VT[tri[:,3]-1]+VT[tri[:,5]-1])/3.0
A=np.asarray(Image.open("/root/av/tex/texture_1001.png").convert("RGB"),dtype=np.float32)
H,W,_=A.shape
ax=np.clip((cuv[:,0]*W).astype(int),0,W-1); ay=np.clip(((1-cuv[:,1])*H).astype(int),0,H-1)
texc=A[ay,ax]                                     # OBJ vt 左下原点
I0=intr[views[0]["intrinsicId"]]
print("intrinsic keys:", [k for k in I0 if k in ("focalLength","sensorWidth","pixelRatio","principalPoint","width","height","type")])
def K_of(iid):
    I=intr[iid]; w=float(I["width"]); h=float(I["height"])
    f=float(I["focalLength"])/float(I["sensorWidth"])*w      # mm -> px
    pp=[float(x) for x in I["principalPoint"]]
    return f, (pp[0]+w/2 if abs(pp[0])<w/4 else pp[0]), (pp[1]+h/2 if abs(pp[1])<h/4 else pp[1]), w, h
for conv in ("R(X-C)","R^T(X-C)"):
    inside=0; tot=0; vals=[]; texs=[]
    for v in views[::4]:
        T=poses[v["poseId"]]
        R=np.array([float(x) for x in T["rotation"]]).reshape(3,3)
        C=np.array([float(x) for x in T["center"]])
        Rm = R if conv=="R(X-C)" else R.T
        Xc=(Rm@(c3-C).T).T
        f,cx,cy,w,h=K_of(v["intrinsicId"])
        z=Xc[:,2]
        ok=z>1e-6
        u=f*Xc[:,0]/np.where(ok,z,1)+cx; vv=f*Xc[:,1]/np.where(ok,z,1)+cy
        ok&= (u>=0)&(u<w)&(vv>=0)&(vv<h)
        inside+=ok.sum(); tot+=len(ok)
        if ok.sum() and conv=="R(X-C)":
            im=np.asarray(Image.open(v["path"]).convert("RGB"),dtype=np.float32)
            vals.append(im[vv[ok].astype(int),u[ok].astype(int)]); texs.append(texc[ok])
    print(f"{conv:10s} 投影落在画面内 {100*inside/tot:5.1f}%")
    if conv=="R(X-C)" and vals:
        src=np.concatenate(vals); tx=np.concatenate(texs)
        print(f"  配对样本 {len(src)}")
        q=[10,25,50,75,90]
        print("  分位     ", "  ".join(f"p{x:<3d}" for x in q))
        print("  源图     ", "  ".join(f"{x:5.1f}" for x in np.percentile(src,q)))
        print("  图集     ", "  ".join(f"{x:5.1f}" for x in np.percentile(tx,q)))
        def enc(x): x=np.clip(x/255,0,1); return 255*np.where(x<=0.0031308,12.92*x,1.055*x**(1/2.4)-0.055)
        print("  图集→sRGB", "  ".join(f"{x:5.1f}" for x in np.percentile(enc(tx),q)))
