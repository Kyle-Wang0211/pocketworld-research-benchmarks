# infinigen2-flying-indoors 一个场景(4 轨迹 x 左右 x 24 帧)的视角重叠, 与 WMG/我们自己渲的用同一把尺子:
# 官方 Infinigen 共视函数 (converter 里逐字移植的 ig_covisibility), 1/2 分辨率。
import importlib.util, glob, os, numpy as np, cv2
from multiprocessing import Pool
spec=importlib.util.spec_from_file_location("conv","/root/infinigen_to_blend.py"); conv=importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)
S=0.5; V=[]; meta=[]
for tr in sorted(glob.glob("/root/ig2fly/out/*_traj*")):
    t_id=int(tr[-1])
    for cam in ("CameraLeft","CameraRight"):
        z=np.load(f"{tr}/{cam}/camera.npz") if os.path.exists(f"{tr}/{cam}/camera.npz") else np.load(glob.glob(f"{tr}/camera-{cam}.npz")[0])
        for f in range(24):
            d=np.load(f"{tr}/{cam}/depth_{f:04d}.npy").astype(np.float32); d[~np.isfinite(d)]=0
            K=z["K"][f].astype(np.float64).copy(); h,w=int(d.shape[0]*S),int(d.shape[1]*S)
            d=cv2.resize(d,(w,h),interpolation=cv2.INTER_NEAREST); K[:2]*=S
            V.append((d,K,z["T"][f].astype(np.float64))); meta.append((t_id,cam,f))
n=len(V); print("视角数", n)
refs=[i for i,(t,c,f) in enumerate(meta) if c=="CameraLeft" and f in (0,12,23)]
def job(ij):
    i,j=ij; di,Ki,Ti=V[i]; dj,Kj,Tj=V[j]; return i,j,conv.ig_covisibility(di,dj,Ki,Kj,Ti,Tj)
with Pool(16) as p: res=p.map(job,[(i,j) for i in refs for j in range(n) if j!=i])
C={}
for i,j,c in res: C.setdefault(i,{})[j]=c
same=[];allv=[];n30s=[];n30a=[]
for i in refs:
    t,c,f=meta[i]
    s=sorted([C[i][j] for j in C[i] if meta[j][2]==f],reverse=True)          # 同一时刻其余 7 张
    a=sorted(C[i].values(),reverse=True)                                    # 全部 191 张
    same.append(s[6] if len(s)>6 else 0); allv.append(a[6]); n30s.append(sum(x>=0.3 for x in s)); n30a.append(sum(x>=0.3 for x in a))
print("参考图 %d 张 (4 轨迹 x 第 0/12/23 帧的左目)"%len(refs))
print("取法1 同一时刻 8 张: 第7邻居共视 中位 %.3f (最差 %.3f) | 共视>=30%% 的邻居数 中位 %d | 凑齐 7 个的参考图 %.0f%%"%(np.median(same),np.min(same),np.median(n30s),100*np.mean(np.array(n30s)>=7)))
print("取法2 全场景 192 张: 第7邻居共视 中位 %.3f (最差 %.3f) | 共视>=30%% 的邻居数 中位 %d | 凑齐 7 个的参考图 %.0f%%"%(np.median(allv),np.min(allv),np.median(n30a),100*np.mean(np.array(n30a)>=7)))
# 同一轨迹相邻帧 (看动态物体影响): 参考帧 f 与 f+1..f+3 的共视
adj=[C[i][j] for i in refs for j in C[i] if meta[j][0]==meta[i][0] and meta[j][1]=="CameraLeft" and 1<=meta[j][2]-meta[i][2]<=3]
print("同轨迹相邻 1-3 帧的共视 中位 %.3f"%np.median(adj) if adj else "")
