# [显存剖析 2026-08-31] 132 视图 17 GiB 花在哪?分段量峰值。
import os,time,threading,resource,numpy as np,torch
def guard(cap=10*2**30):
    while True:
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>cap:
            print("🔴 守卫,自杀",flush=True); os._exit(9)
        time.sleep(0.3)
threading.Thread(target=guard,daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from uniception.models.encoders import ViTEncoderInput
N=int(os.environ.get("N","48"))
m=MapAnything.from_pretrained("weights/v1").to("mps").eval()
base=torch.mps.driver_allocated_memory()
print(f"  权重驻留 {base/2**30:.2f} GiB",flush=True)
views=load_images("images_rgb")[:N]
imgs=torch.cat([v["img"] for v in views],0).to("mps")
NORM=views[0]["data_norm_type"][0]
torch.mps.empty_cache(); b2=torch.mps.driver_allocated_memory()
# ① 编码器:一次全量 vs 分小批
with torch.inference_mode(), torch.autocast("mps",dtype=torch.float16):
    t=time.time(); out=m.encoder(ViTEncoderInput(image=imgs,data_norm_type=NORM))
    torch.mps.synchronize()
    p1=torch.mps.driver_allocated_memory()
    print(f"  ① 编码器 N={N} 一次全量: 峰值 {p1/2**30:5.2f} GiB (增量 {(p1-b2)/2**30:.2f})  {time.time()-t:.1f}s",flush=True)
    f_full=out.features.clone(); del out
torch.mps.empty_cache(); b3=torch.mps.driver_allocated_memory()
with torch.inference_mode(), torch.autocast("mps",dtype=torch.float16):
    t=time.time(); fs=[]
    for i in range(0,N,8):
        o=m.encoder(ViTEncoderInput(image=imgs[i:i+8],data_norm_type=NORM))
        fs.append(o.features.clone()); del o
    torch.mps.synchronize()
    p2=torch.mps.driver_allocated_memory()
    f_mb=torch.cat(fs,0); del fs
    print(f"  ② 编码器 分8批:        峰值 {p2/2**30:5.2f} GiB (增量 {(p2-b3)/2**30:.2f})  {time.time()-t:.1f}s",flush=True)
d=(f_full.float()-f_mb.float()).abs().max().item()
print(f"  ⇒ 分批与全量特征最大差 {d:.3e}  {'✅ 逐位相同' if d==0 else '⚠️ 有差异'}",flush=True)
print(f"  ⇒ 编码器省下 {(p1-b2-(p2-b3))/2**30:.2f} GiB",flush=True)
