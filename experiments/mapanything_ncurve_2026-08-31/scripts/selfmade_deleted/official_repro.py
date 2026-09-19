# [官方复刻 2026-08-31] 逐字复刻 gradio_app.py + utils/hf_utils/viz.py 的取点与过滤链。
# 🔑 与我之前做法的关键差别:
#   1. infer 参数朴素:apply_mask=True, mask_edges=True,**不传** apply_confidence_mask
#      (官方 gradio_app.py:134 就三个参数)
#   2. 置信度过滤在**导出层**做,且是**全局分位**(viz.py:231 把 132 帧 conf 摊平后取
#      np.percentile) —— 我之前用 infer 的 apply_confidence_mask 是**逐视图**分位,
#      会保留每帧里最好的那部分,哪怕整帧都很差。这是雾的真正来源之一。
#   3. 官方默认 conf_thres=3.0(第3百分位),外加 mask_black_bg / mask_white_bg
import os, sys, time, numpy as np, torch
from pathlib import Path
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from mapanything.utils.geometry import depthmap_to_world_frame

CONF = float(sys.argv[1]) if len(sys.argv)>1 else 3.0
BLACK = "-b" in sys.argv; WHITE = "-w" in sys.argv
TAG = sys.argv[2] if len(sys.argv)>2 else f"off{CONF:g}"
m=MapAnything.from_pretrained(os.environ.get("MA_W","weights/v1")).to("mps").eval()
views=load_images("images_rgb")
t=time.time()
with torch.inference_mode():
    outs=m.infer(views, apply_mask=True, mask_edges=True,
                 memory_efficient_inference=True, minibatch_size=1)   # 显存所限,官方是 False
torch.mps.synchronize(); infer_s=time.time()-t

W=[];C=[];CF=[];FM=[]
for p in outs:
    d=p["depth_z"][0].squeeze(-1)
    pts,valid=depthmap_to_world_frame(d, p["intrinsics"][0], p["camera_poses"][0])
    mk=p["mask"][0].squeeze(-1).cpu().numpy().astype(bool) & valid.cpu().numpy()
    W.append(pts.cpu().numpy()); FM.append(mk)
    C.append(p["img_no_norm"][0].cpu().numpy()); CF.append(p["conf"][0].squeeze(-1).cpu().numpy())
V=np.stack(W).reshape(-1,3); col=np.stack(C).reshape(-1,3); conf=np.stack(CF).reshape(-1)
fm=np.stack(FM).reshape(-1)
if col.max()<=1.0: col=col*255.0
col=np.clip(col,0,255).astype(np.uint8)

mask=np.ones(len(V),bool)
thr=np.percentile(conf, CONF)                      # 🔑 全局分位,不是逐视图
mask &= conf>=thr
if BLACK: mask &= col.sum(1)>=16
if WHITE: mask &= ~((col[:,0]>240)&(col[:,1]>240)&(col[:,2]>240))
mask &= fm                                          # mask_ambiguous(官方默认勾选)
V=V[mask]; col=col[mask]
D=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
a=np.empty(len(V),dtype=D); a["x"],a["y"],a["z"]=V[:,0],V[:,1],V[:,2]
a["r"],a["g"],a["b"]=col[:,0],col[:,1],col[:,2]
Path(f"off_{TAG}").mkdir(exist_ok=True)
with open(f"off_{TAG}/cloud.ply","wb") as f:
    f.write((f"ply\nformat binary_little_endian 1.0\nelement vertex {len(V)}\n"
             "property float x\nproperty float y\nproperty float z\n"
             "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode())
    f.write(a.tobytes())
med=np.median(V,0); r=float(np.linalg.norm(np.percentile(V,90,axis=0)-med))
lo,hi=np.percentile(V,5,axis=0),np.percentile(V,95,axis=0)
print(f"  {TAG:10s} conf{CONF:g}{' +黑' if BLACK else ''}{' +白' if WHITE else ''}  "
      f"{len(V):>11,d} 点  radius {r:.2f}  "
      f"p5-p95对角 {np.linalg.norm(hi-lo):.2f}  推理{infer_s:.0f}s", flush=True)
