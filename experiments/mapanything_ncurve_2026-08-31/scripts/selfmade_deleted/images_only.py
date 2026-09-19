# [纯图像 2026-08-31] 复刻 08-26 基准的跑法:**不喂位姿**,模型自估。
# 依据:该 run.json 只记了 image_folder,没有 cams;输出 24,394,262 点
#      = 132×518×392 的 91.0%,与"纯图像 + 官方 mask"吻合。
import time, numpy as np, torch, os
from pathlib import Path
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from mapanything.utils.geometry import depthmap_to_world_frame
m=MapAnything.from_pretrained("weights/v1").to("mps").eval()
views=load_images("images_rgb")
print(f"  载入 {len(views)} 视图 shape={tuple(views[0]['img'].shape)}", flush=True)
t=time.time()
with torch.inference_mode():
    outs=m.infer(views, memory_efficient_inference=True, minibatch_size=1, use_amp=True,
                 amp_dtype="fp16", apply_mask=True, mask_edges=True)
torch.mps.synchronize(); print(f"  推理 {time.time()-t:.1f}s", flush=True)
X=[];C=[]
for i,p in enumerate(outs):
    d=p["depth_z"][0].squeeze(-1)                    # 纯图像:用模型**自己**的内参与位姿
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
arr=np.empty(len(X),dtype=D)
arr["x"],arr["y"],arr["z"]=X[:,0],X[:,1],X[:,2]; arr["r"],arr["g"],arr["b"]=C[:,0],C[:,1],C[:,2]
Path("rgb_imgonly").mkdir(exist_ok=True)
with open("rgb_imgonly/cloud.ply","wb") as f:
    f.write((f"ply\nformat binary_little_endian 1.0\nelement vertex {len(X)}\n"
             "property float x\nproperty float y\nproperty float z\n"
             "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n").encode())
    f.write(arr.tobytes())
print(f"  {len(X):,d} 点 ({len(X)/26803392*100:.1f}% of 全像素)  包围盒 {np.round(X.max(0)-X.min(0),2)}")
