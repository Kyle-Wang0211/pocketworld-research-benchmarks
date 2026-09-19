# [重影对照 2026-08-31] posed vs unposed,唯一变量=是否喂 COLMAP 位姿。
# 重影量化:把视图 j 的世界点投进视图 i 的相机,与 i 自己的深度图比 |Δz|/z 中位数。
# 两版共面 ⇒ 该值小;错开两层皮 ⇒ 该值大。用**各自的**位姿投影(unposed 用模型预测的)。
import os,sys,time,threading,resource,json,numpy as np,torch
from pathlib import Path
LIM=float(os.environ.get("CAP_GIB","13"))
threading.Thread(target=lambda:[(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**30>LIM and (print("🔴守卫",flush=True),os._exit(9)),time.sleep(0.3)) for _ in iter(int,1)],daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import preprocess_inputs
from minibatch_encoder import wrap
from PIL import Image
N=int(os.environ.get("N","132")); BS=int(os.environ.get("BS","8")); POSED=os.environ.get("POSED","1")=="1"
FR=Path.home()/".codex/builds/pw-dense-xorwow-2000-20260829/FrozenB28"
sel=json.loads((FR/"selection.json").read_text())["images"][:N]
raw=[]
for im in sel:
    d={"img":np.asarray(Image.open(f"images_rgb/{im['name']}").convert("RGB"),dtype=np.uint8)}
    if POSED:
        R=np.array(im["R"],np.float64).reshape(3,3); T=np.array(im["T"],np.float64)
        w2c=np.eye(4); w2c[:3,:3]=R; w2c[:3,3]=T
        d.update(intrinsics=np.array(im["K"],np.float32).reshape(3,3),
                 camera_poses=np.linalg.inv(w2c).astype(np.float32),
                 is_metric_scale=torch.tensor([False]))
    raw.append(d)
views=preprocess_inputs(raw, verbose=False)
m=wrap(MapAnything.from_pretrained(os.environ.get("MA_W","weights/v1")).to("mps").eval(), BS)
kw=dict(memory_efficient_inference=True,minibatch_size=1,use_amp=True,amp_dtype="bf16",
        apply_mask=True,mask_edges=True)
if POSED: kw.update(ignore_depth_inputs=True,ignore_depth_scale_inputs=True,ignore_pose_scale_inputs=True)
t=time.time()
with torch.inference_mode(): outs=m.infer(views,**kw)
torch.mps.synchronize(); print(f"  infer {time.time()-t:.0f}s",flush=True)
D=[];K=[];P=[];M=[]
for i,p in enumerate(outs):
    D.append(p["depth_z"][0].squeeze(-1).float().cpu().numpy())
    M.append(p["mask"][0].squeeze(-1).cpu().numpy().astype(bool))
    # posed 时用**我们给的**外参;unposed 时只能用模型预测的
    K.append((views[i]["intrinsics"][0] if POSED else p["intrinsics"][0]).float().cpu().numpy())
    P.append((views[i]["camera_poses"][0] if POSED else p["camera_poses"][0]).float().cpu().numpy())
tag="posed" if POSED else "unposed"
np.savez_compressed(f"dpk_{tag}.npz",D=np.stack(D).astype(np.float16),M=np.stack(M),
                    K=np.stack(K),P=np.stack(P))
print(f"  ✅ dpk_{tag}.npz",flush=True)
