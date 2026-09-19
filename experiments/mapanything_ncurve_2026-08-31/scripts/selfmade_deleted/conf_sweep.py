# [置信度扫描 2026-08-31] use_multiview_confidence = 多视图深度一致性
# (multiview_conf_depth_abs/rel_thresh 各 0.02) —— 这是 COLMAP 稠密
# 几何一致性过滤的等价物。之前所有臂都没开它,所以全是雾。
import sys, time, numpy as np, torch
from pathlib import Path
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from mapanything.utils.geometry import depthmap_to_world_frame
PCT=float(sys.argv[1]); MV = sys.argv[2]=="1"; TAG=sys.argv[3]
m=MapAnything.from_pretrained("weights/v1").to("mps").eval()
views=load_images("images_rgb")
t=time.time()
with torch.inference_mode():
    outs=m.infer(views, memory_efficient_inference=True, minibatch_size=1, use_amp=True,
                 amp_dtype="fp16", apply_mask=True, mask_edges=True,
                 apply_confidence_mask=(PCT>0), confidence_percentile=PCT,
                 use_multiview_confidence=MV)
torch.mps.synchronize()
X=[];C=[]
for p in outs:
    d=p["depth_z"][0].squeeze(-1)
    xyz,valid=depthmap_to_world_frame(d, p["intrinsics"][0], p["camera_poses"][0])
    mk=p["mask"][0].squeeze(-1).bool() & valid.bool() & torch.isfinite(xyz).all(-1)
    X.append(xyz[mk].float().cpu().numpy())
    c=p["img_no_norm"][0][mk].cpu().numpy()
    if c.dtype!=np.uint8:
        if float(c.max(initial=0))<=1.0: c=c*255.0
        c=np.clip(c,0,255).astype(np.uint8)
    C.append(c)
X=np.concatenate(X); C=np.concatenate(C)
D=np.dtype([("x","<f4"),("y","<f4"),("z","<f4"),("r","u1"),("g","u1"),("b","u1")])
a=np.empty(len(X),dtype=D); a["x"],a["y"],a["z"]=X[:,0],X[:,1],X[:,2]
a["r"],a["g"],a["b"]=C[:,0],C[:,1],C[:,2]
Path(f"arm_{TAG}").mkdir(exist_ok=True)
with open(f"arm_{TAG}/cloud.ply","wb") as f:
    f.write((f"ply\nformat binary_little_endian 1.0\nelement vertex {len(X)}\n"
             "property float x\nproperty float y\nproperty float z\n"
             "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode())
    f.write(a.tobytes())
ext=X.max(0)-X.min(0); med=np.median(X,0)
r=float(np.linalg.norm(np.percentile(X,90,axis=0)-med))
print(f"  {TAG:14s} MV={MV} pct={PCT:5.1f}  {len(X):>11,d} 点 ({len(X)/26803392*100:5.1f}%)  "
      f"包围盒 {np.round(ext,1)}  radius {r:.2f}  {time.time()-t:.0f}s", flush=True)
