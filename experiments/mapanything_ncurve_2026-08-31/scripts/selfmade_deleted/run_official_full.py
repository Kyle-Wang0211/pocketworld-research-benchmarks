# [官方全参 2026-08-31] 抄全 README 的 infer 参数表,不再漏 3 个置信度开关。
#   use_multiview_confidence=True  ← 官方版消重影:像素投到所有重叠视图,深度对不上判 outlier
#   apply_confidence_mask=True / confidence_percentile=10  ← 官方默认的低置信剔除
# 位姿保持不喂(已量证:喂 COLMAP 位姿重影 5.24% vs 纯图像 2.59%,更差)。
import os,time,threading,resource,numpy as np,torch
from pathlib import Path
LIM=float(os.environ.get("CAP_GIB","13"))
threading.Thread(target=lambda:[(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**30>LIM and (print("🔴守卫",flush=True),os._exit(9)),time.sleep(0.3)) for _ in iter(int,1)],daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from minibatch_encoder import wrap
N=int(os.environ.get("N","132")); BS=int(os.environ.get("BS","8"))
MV=os.environ.get("MV","1")=="1"; TAG=os.environ.get("TAG","mvconf")
files=sorted(Path("images_rgb").glob("*"))[:N]
views=load_images([str(p) for p in files])          # ← 官方入口,不用我自己的预处理
m=wrap(MapAnything.from_pretrained(os.environ.get("MA_W","weights/v1")).to("mps").eval(), BS)
pk=[0]
threading.Thread(target=lambda:[pk.__setitem__(0,max(pk[0],torch.mps.driver_allocated_memory())) or time.sleep(0.05) for _ in iter(int,1)],daemon=True).start()
t=time.time()
with torch.inference_mode():
    outs=m.infer(views, memory_efficient_inference=True, minibatch_size=1,
                 use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True,
                 apply_confidence_mask=True, confidence_percentile=10,
                 use_multiview_confidence=MV)
torch.mps.synchronize()
print(f"  N={N} mvconf={MV}  {time.time()-t:.0f}s  MPS峰值 {pk[0]/2**30:.2f} GiB",flush=True)
D=[];K=[];P=[];M=[];C=[];keep=0;tot=0
for i,p in enumerate(outs):
    D.append(p["depth_z"][0].squeeze(-1).float().cpu().numpy())
    mk=p["mask"][0].squeeze(-1).cpu().numpy().astype(bool); M.append(mk)
    C.append(p["conf"][0].float().cpu().numpy())
    K.append(p["intrinsics"][0].float().cpu().numpy()); P.append(p["camera_poses"][0].float().cpu().numpy())
    keep+=int(mk.sum()); tot+=mk.size
np.savez_compressed(f"dpk_{TAG}.npz",D=np.stack(D).astype(np.float16),M=np.stack(M),
                    K=np.stack(K),P=np.stack(P),C=np.stack(C).astype(np.float16))
print(f"  存活像素 {keep/1e6:.2f}M / {tot/1e6:.2f}M = {100*keep/tot:.1f}%   ✅ dpk_{TAG}.npz",flush=True)
