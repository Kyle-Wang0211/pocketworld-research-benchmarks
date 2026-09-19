# [后端对拍 2026-08-31] MPS vs CPU。假设:PyTorch MPS 后端有算子缺陷,
# 导致 Mac 上的结果与 5090(CUDA)系统性不同 —— 这能解释为什么我调什么参数都不对。
# CPU 是最可信的参照(算子实现最成熟)。8 视图,内存安全。
import os, time, resource, threading, numpy as np, torch
def guard(cap=9*2**30):
    while True:
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>cap:
            print("🔴 内存守卫,自杀",flush=True); os._exit(9)
        time.sleep(0.5)
threading.Thread(target=guard,daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from mapanything.utils.geometry import depthmap_to_world_frame
N=8
allv=load_images("images_rgb")[:N]
res={}
for dev in ("cpu","mps"):
    m=MapAnything.from_pretrained("weights/v1").to(dev).eval()
    views=[{k:(v.to(dev) if torch.is_tensor(v) else v) for k,v in d.items()} for d in allv]
    t=time.time()
    with torch.inference_mode():
        outs=m.infer(views, apply_mask=True, mask_edges=True,
                     memory_efficient_inference=True, minibatch_size=1,
                     use_amp=False)          # 关 amp,排除混合精度干扰
    dt=time.time()-t
    D=[];P=[]
    for p in outs:
        d=p["depth_z"][0].squeeze(-1)
        pts,valid=depthmap_to_world_frame(d,p["intrinsics"][0],p["camera_poses"][0])
        mk=p["mask"][0].squeeze(-1).bool()&valid.bool()&torch.isfinite(pts).all(-1)
        D.append(d.float().cpu().numpy()); P.append(pts[mk].float().cpu().numpy())
    res[dev]=(np.stack(D), np.concatenate(P), dt)
    del m, outs
    print(f"  {dev:4s} {dt:6.1f}s  深度中位 {np.median(res[dev][0]):.4f}  "
          f"点数 {len(res[dev][1]):,d}",flush=True)
dc,dm=res["cpu"][0],res["mps"][0]
rel=np.abs(dm-dc)/np.maximum(np.abs(dc),1e-6)
print(f"\n  深度图 CPU vs MPS:")
print(f"    最大绝对差 {np.abs(dm-dc).max():.5f}   中位相对差 {np.median(rel)*100:.4f}%")
print(f"    p99 相对差 {np.percentile(rel,99)*100:.3f}%   >1% 的像素占比 {(rel>0.01).mean()*100:.2f}%")
