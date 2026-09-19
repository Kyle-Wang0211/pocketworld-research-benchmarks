# [132 视图 2026-08-31] 编码器分批(逐位等价,已验证)让全量能在 18GB Mac 上跑。
import os,sys,time,threading,resource,numpy as np,torch
from pathlib import Path
LIM=float(os.environ.get("CAP_GIB","12.0"))
def guard():
    while True:
        r=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**30
        if r>LIM: print(f"🔴 RSS {r:.1f} GiB > {LIM},自杀",flush=True); os._exit(9)
        time.sleep(0.3)
threading.Thread(target=guard,daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from mapanything.utils.geometry import depthmap_to_world_frame
from minibatch_encoder import wrap
N=int(os.environ.get("N","132")); BS=int(os.environ.get("BS","8"))
W=os.environ.get("MA_W","weights/v1"); TAG=os.environ.get("TAG","v1_132")
m=MapAnything.from_pretrained(W).eval()
m=wrap(m.to("mps"), BS)
views=load_images("images_rgb")[:N]
pk=[0]
def poll():
    while True: pk[0]=max(pk[0],torch.mps.driver_allocated_memory()); time.sleep(0.05)
threading.Thread(target=poll,daemon=True).start()
t=time.time()
with torch.inference_mode():
    outs=m.infer(views, memory_efficient_inference=True, minibatch_size=1,
                 use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)
torch.mps.synchronize(); dt=time.time()-t
print(f"  N={N} BS={BS}  {dt:.0f}s  MPS峰值 {pk[0]/2**30:.2f} GiB  "
      f"RSS峰值 {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**30:.2f} GiB",flush=True)
import trimesh
from mapanything.utils.viz import predictions_to_glb
WP=[];IM=[];MK=[]
for i in range(len(outs)):
    p=outs[i]
    d=p["depth_z"][0].squeeze(-1)
    pts,valid=depthmap_to_world_frame(d,p["intrinsics"][0],p["camera_poses"][0])
    mk=p["mask"][0].squeeze(-1).cpu().numpy().astype(bool)&valid.cpu().numpy()
    WP.append(pts.cpu().numpy()); IM.append(p["img_no_norm"][0].cpu().numpy()); MK.append(mk)
    outs[i]=None                      # 逐视图搬完就释放,别在 MPS 上堆 132 份
    del p,d,pts,valid
    if i%16==15: torch.mps.empty_cache()
pred={"world_points":np.stack(WP),"images":np.stack(IM),"final_masks":np.stack(MK)}
scene=predictions_to_glb(pred, as_mesh=True)
Path(f"mesh_{TAG}").mkdir(exist_ok=True)
scene.export(f"mesh_{TAG}/mesh.glb")
print(f"  ✅ mesh_{TAG}/mesh.glb  {os.path.getsize(f'mesh_{TAG}/mesh.glb')/2**20:.0f} MB",flush=True)
