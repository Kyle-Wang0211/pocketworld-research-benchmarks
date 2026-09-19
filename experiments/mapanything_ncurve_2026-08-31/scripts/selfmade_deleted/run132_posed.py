# [132 视图 + 已知位姿 2026-08-31] 攻重影。
# 重影根因:纯图像模式下 MapAnything **自己估位姿**,每视图网格按它估的外参摆放,
#          估偏一点两个表面就错开 ⇒ 两层皮。官方原版(零修改、无分批)同样有重影,
#          所以重影**不是**编码器分批造成的(分批已逐位对拍:特征差 0.000e+00)。
# 做法:喂 COLMAP 的内参+位姿,所有视图按同一套外参对齐。
# ⚠️ B28 是 COLMAP 位姿 = **无尺度** ⇒ 契约必须 metric_poses=False
#    (我之前误当成 ARKit 米制位姿设了 True,那是错的)。
import os,sys,time,threading,resource,json,numpy as np,torch
from pathlib import Path
LIM=float(os.environ.get("CAP_GIB","13"))
def guard():
    while True:
        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**30>LIM:
            print("🔴 守卫,自杀",flush=True); os._exit(9)
        time.sleep(0.3)
threading.Thread(target=guard,daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import preprocess_inputs
from mapanything.utils.geometry import depthmap_to_world_frame
from mapanything.utils.viz import predictions_to_glb
from minibatch_encoder import wrap
from PIL import Image
N=int(os.environ.get("N","132")); BS=int(os.environ.get("BS","8"))
TAG=os.environ.get("TAG","posed132")
FR=Path.home()/".codex/builds/pw-dense-xorwow-2000-20260829/FrozenB28"
sel=json.loads((FR/"selection.json").read_text())["images"][:N]
raw=[]
for im in sel:
    R=np.array(im["R"],dtype=np.float64).reshape(3,3); T=np.array(im["T"],dtype=np.float64)
    w2c=np.eye(4); w2c[:3,:3]=R; w2c[:3,3]=T
    raw.append({"img":np.asarray(Image.open(f"images_rgb/{im['name']}").convert("RGB"),dtype=np.uint8),
                "intrinsics":np.array(im["K"],dtype=np.float32).reshape(3,3),
                "camera_poses":np.linalg.inv(w2c).astype(np.float32),
                "is_metric_scale":torch.tensor([False])})   # COLMAP 位姿无尺度
views=preprocess_inputs(raw, verbose=False)
m=wrap(MapAnything.from_pretrained(os.environ.get("MA_W","weights/v1")).to("mps").eval(), BS)
pk=[0]
threading.Thread(target=lambda:[pk.__setitem__(0,max(pk[0],torch.mps.driver_allocated_memory())) or time.sleep(0.05) for _ in iter(int,1)],daemon=True).start()
t=time.time()
with torch.inference_mode():
    outs=m.infer(views, memory_efficient_inference=True, minibatch_size=1,
                 use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True,
                 ignore_depth_inputs=True, ignore_depth_scale_inputs=True,
                 ignore_pose_scale_inputs=True)      # 位姿无尺度 ⇒ 忽略其尺度
torch.mps.synchronize()
print(f"  N={N} 已知位姿  {time.time()-t:.0f}s  MPS峰值 {pk[0]/2**30:.2f} GiB",flush=True)
WP=[];IM=[];MK=[]
for i in range(len(outs)):
    p=outs[i]; d=p["depth_z"][0].squeeze(-1)
    # 🔑 用**我们给的**内参位姿重建,不用模型预测的
    pts,valid=depthmap_to_world_frame(d, views[i]["intrinsics"][0].to(d.device),
                                      views[i]["camera_poses"][0].to(d.device))
    mk=p["mask"][0].squeeze(-1).cpu().numpy().astype(bool)&valid.cpu().numpy()
    WP.append(pts.cpu().numpy()); IM.append(p["img_no_norm"][0].cpu().numpy()); MK.append(mk)
    outs[i]=None; del p,d,pts,valid
    if i%16==15: torch.mps.empty_cache()
sc=predictions_to_glb({"world_points":np.stack(WP),"images":np.stack(IM),
                       "final_masks":np.stack(MK)}, as_mesh=True)
Path(f"mesh_{TAG}").mkdir(exist_ok=True); sc.export(f"mesh_{TAG}/mesh.glb")
print(f"  ✅ mesh_{TAG}/mesh.glb {os.path.getsize(f'mesh_{TAG}/mesh.glb')/2**20:.0f} MB",flush=True)
