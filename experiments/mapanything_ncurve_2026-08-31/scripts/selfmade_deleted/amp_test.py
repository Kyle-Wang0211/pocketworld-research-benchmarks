# [精度测试 2026-08-31] fp16/bf16/fp32 对深度的影响。
# 假设:fp16 约 3 位十进制有效数字,深度被量化 ⇒ 点沿视线散开 = "雾"。
# 用 24 视图控内存(之前 132 帧峰值 17 GiB 换页,用户明确要求别再搞爆)。
import os, sys, time, resource, threading, numpy as np, torch
from pathlib import Path
def guard(cap=9*2**30):
    while True:
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>cap:
            print("🔴 内存守卫,自杀",flush=True); os._exit(9)
        time.sleep(0.5)
threading.Thread(target=guard,daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from mapanything.utils.geometry import depthmap_to_world_frame
N=24
m=MapAnything.from_pretrained("weights/v1").to("mps").eval()
allv=load_images("images_rgb"); views=allv[:N]
print(f"  {N} 视图  {tuple(views[0]['img'].shape)}",flush=True)
def run(kw,lab):
    t=time.time()
    with torch.inference_mode():
        outs=m.infer(views, apply_mask=True, mask_edges=True,
                     memory_efficient_inference=True, minibatch_size=1, **kw)
    torch.mps.synchronize(); dt=time.time()-t
    X=[]
    for p in outs:
        d=p["depth_z"][0].squeeze(-1)
        pts,valid=depthmap_to_world_frame(d,p["intrinsics"][0],p["camera_poses"][0])
        mk=p["mask"][0].squeeze(-1).bool()&valid.bool()&torch.isfinite(pts).all(-1)
        X.append(pts[mk].float().cpu().numpy())
    X=np.concatenate(X)
    lo,hi=np.percentile(X,5,axis=0),np.percentile(X,95,axis=0)
    inb=((X>=lo)&(X<=hi)).all(1); vol=float(np.prod(hi-lo))
    print(f"  {lab:16s} {len(X):>9,d} 点  p5-p95对角 {np.linalg.norm(hi-lo):6.3f}  "
          f"盒内密度 {inb.sum()/vol/1000:9.1f} k  {dt:.0f}s",flush=True)
    torch.mps.empty_cache()
run({"use_amp":False},"fp32(不用amp)")
run({"use_amp":True,"amp_dtype":"fp16"},"fp16")
run({"use_amp":True,"amp_dtype":"bf16"},"bf16(官方默认)")
