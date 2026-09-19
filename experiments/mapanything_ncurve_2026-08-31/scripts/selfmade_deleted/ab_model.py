# [giant vs v1 2026-08-31] 唯一变量=模型。其余逐字相同(官方复刻链路)。
# 🔴 32 视图,不跑 132 全量 —— 那个必然 17+ GiB 超 MPS 上限 13.32,今天已因此把机器搞爆两次。
import os, sys, time, resource, threading, numpy as np, torch
from pathlib import Path
def guard(cap=9*2**30):
    while True:
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>cap:
            print("🔴 内存守卫触发,自杀",flush=True); os._exit(9)
        time.sleep(0.5)
threading.Thread(target=guard,daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from mapanything.utils.geometry import depthmap_to_world_frame
W=sys.argv[1]; TAG=sys.argv[2]; N=int(os.environ.get("N","32"))
m=MapAnything.from_pretrained(W).to("mps").eval()
np_=sum(p.numel() for p in m.parameters())
views=load_images("images_rgb")[:N]
t=time.time()
with torch.inference_mode():
    outs=m.infer(views, apply_mask=True, mask_edges=True,
                 memory_efficient_inference=True, minibatch_size=1)
torch.mps.synchronize(); dt=time.time()-t
V=[];C=[]
for p in outs:
    d=p["depth_z"][0].squeeze(-1)
    pts,valid=depthmap_to_world_frame(d,p["intrinsics"][0],p["camera_poses"][0])
    mk=p["mask"][0].squeeze(-1).bool()&valid.bool()&torch.isfinite(pts).all(-1)
    V.append(pts[mk].float().cpu().numpy())
    c=p["img_no_norm"][0][mk].cpu().numpy()
    if c.dtype!=np.uint8:
        if float(c.max(initial=0))<=1.0: c=c*255.0
        c=np.clip(c,0,255).astype(np.uint8)
    C.append(c)
V=np.concatenate(V); C=np.concatenate(C)
D=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
a=np.empty(len(V),dtype=D); a["x"],a["y"],a["z"]=V[:,0],V[:,1],V[:,2]
a["r"],a["g"],a["b"]=C[:,0],C[:,1],C[:,2]
Path(f"ab_{TAG}").mkdir(exist_ok=True)
with open(f"ab_{TAG}/cloud.ply","wb") as f:
    f.write((f"ply\nformat binary_little_endian 1.0\nelement vertex {len(V)}\n"
             "property float x\nproperty float y\nproperty float z\n"
             "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode())
    f.write(a.tobytes())
lo,hi=np.percentile(V,5,axis=0),np.percentile(V,95,axis=0)
diag=float(np.linalg.norm(hi-lo)); Vn=V/diag
lo2,hi2=np.percentile(Vn,5,axis=0),np.percentile(Vn,95,axis=0)
inb=((Vn>=lo2)&(Vn<=hi2)).all(1)
print(f"  {TAG:7s} {np_/1e6:6.0f}M参数  {len(V):>9,d}点  {dt:5.0f}s  "
      f"归一化密度 {inb.sum()/float(np.prod(hi2-lo2))/1e6:7.2f}M",flush=True)
