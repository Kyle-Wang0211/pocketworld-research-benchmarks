# WMGStereo 能否用于 MVS 训练: 用官方 Infinigen 共视函数 (converter 里逐字移植的 ig_covisibility,
# process_mvs_data.py:85-107) 量「每张参考图第 7 好邻居的共视比例」, 与我们自己渲的房间同一把尺子比。
# WMG 深度 = 官方 InfinigenStereo util_scripts.py:139-142 depth_from_disparity (Z=f*B/d, d>0), B=左右相机中心距离。
# 为省时两边都降到 1/2 分辨率 (深度最近邻, K 同比缩放)。
import importlib.util, glob, os, sys, re, numpy as np, cv2
from multiprocessing import Pool
spec=importlib.util.spec_from_file_location("conv","/root/infinigen_to_blend.py"); conv=importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)
S=0.5
def half(d,K):
    H,W=d.shape; h,w=int(H*S),int(W*S)
    d2=cv2.resize(d.astype(np.float32),(w,h),interpolation=cv2.INTER_NEAREST); K2=K.copy().astype(np.float64); K2[:2]*=S
    return d2,K2
def idx(f): return int(re.search(r"_(\d+)_0_0048_0",os.path.basename(f)).group(1))
def load_wmg(root, scale=1.0):
    V=[]
    for f in sorted(glob.glob(root+"/frames/disparity/camera_0/disparity_*_0_0048_0.npy"),key=idx):
        k=idx(f); zL=np.load(root+f"/frames/camview/camera_0/camview_{k}_0_0048_0.npz"); zR=np.load(root+f"/frames/camview/camera_1/camview_{k}_0_0048_1.npz")
        B=float(np.linalg.norm(zL["T"][:3,3]-zR["T"][:3,3])); disp=np.load(f).astype(np.float32)
        with np.errstate(divide="ignore",invalid="ignore"): Z=np.where(disp>0, zL["K"][0,0]*B/disp, 0.0).astype(np.float32)
        d,K=half(Z*scale,zL["K"]); V.append((d,K,zL["T"].astype(np.float64)))
    return V
def load_ig(root):
    V=[]
    for f in sorted(glob.glob(root+"/frames/Depth/camera_0/Depth_*_0_0048_0.npy"),key=idx):
        k=idx(f); z=np.load(root+f"/frames/camview/camera_0/camview_{k}_0_0048_0.npz"); d=np.load(f).astype(np.float32); d[~np.isfinite(d)]=0
        d,K=half(d,z["K"]); V.append((d,K,z["T"].astype(np.float64)))
    return V
G={}
def pair(ij):
    i,j=ij; di,Ki,Ti=G["V"][i]; dj,Kj,Tj=G["V"][j]
    return i,j,conv.ig_covisibility(di,dj,Ki,Kj,Ti,Tj)
def room(tag, V):
    G["V"]=V; n=len(V); M=np.zeros((n,n))
    with Pool(12) as p:
        for i,j,c in p.map(pair,[(i,j) for i in range(n) for j in range(n) if i!=j]): M[i,j]=c
    top=np.sort(M,axis=1)[:,::-1]            # 每行降序 (对角 0 排最后)
    k7=top[:,6]; n30=(M>=0.3).sum(1)
    return dict(tag=tag,n=n,k1=np.median(top[:,0]),k7=np.median(k7),k7_p25=np.percentile(k7,25),
                ref_ok=np.mean(n30>=7), n30_med=np.median(n30))
out=[]
wmg=sorted(d for d in glob.glob("/root/wmg_probe/*") if os.path.isdir(d+"/frames"))
for r in wmg: out.append(room("WMG "+os.path.basename(r), load_wmg(r))); print(out[-1],flush=True)
out.append(room("阴性对照 WMG 深度×1.2 "+os.path.basename(wmg[0]), load_wmg(wmg[0],1.2))); print(out[-1],flush=True)
for r in ["/root/ig7_official/356d69c6","/root/ig7_official/157b9161","/root/ig7_official/6e081a66"]:
    out.append(room("我们-完整配方 "+os.path.basename(r), load_ig(r))); print(out[-1],flush=True)
fast=[d for d in sorted(glob.glob("/root/ig7_official_e/*")) if len(glob.glob(d+"/frames/Depth/camera_0/Depth_*.npy"))>=30][:3]
for r in fast: out.append(room("我们-fast_solve "+os.path.basename(r), load_ig(r))); print(out[-1],flush=True)
print("\n%-34s %4s %8s %8s %8s %10s %8s"%("房间","视角","最好邻居","第7邻居","第7(p25)","凑齐7个≥30%","≥30%个数"))
for o in out: print("%-34s %4d %8.3f %8.3f %8.3f %10.0f%% %8.0f"%(o["tag"],o["n"],o["k1"],o["k7"],o["k7_p25"],100*o["ref_ok"],o["n30_med"]))
