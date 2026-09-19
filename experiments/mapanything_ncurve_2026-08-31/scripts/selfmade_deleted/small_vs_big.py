# 同样 8 张图:单独喂 8 张 vs 从 132 张那次前向里取出这 8 张。肉眼看谁对齐。
import os,time,threading,resource,numpy as np
from pathlib import Path
LIM=13.0
threading.Thread(target=lambda:[(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**30>LIM and (print("🔴守卫",flush=True),os._exit(9)),time.sleep(0.3)) for _ in iter(int,1)],daemon=True).start()
import torch
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from mapanything.utils.hf_utils.viz import image_mesh
from minibatch_encoder import wrap
SEL=list(range(0,32,4))                      # 8 张,跨度与 132 版取样一致
files=[str(p) for p in sorted(Path("images_rgb").glob("*"))[:132]]
MEAN=np.array([0.485,0.456,0.406],np.float32); STD=np.array([0.229,0.224,0.225],np.float32)
def emit(tag,D,M,K,P,IM):
    u,v=np.meshgrid(np.arange(D.shape[2],dtype=np.float32),np.arange(D.shape[1],dtype=np.float32))
    V=[];C=[];F=[];off=0
    for i in range(len(D)):
        d=D[i];k=K[i];p=P[i]
        x=(u-k[0,2])/k[0,0]*d; y=(v-k[1,2])/k[1,1]*d
        pts=(np.stack([x,y,d],-1)@p[:3,:3].T+p[:3,3]).astype(np.float32)
        if M[i].sum()<500: continue
        f,vv,cc=image_mesh(pts*np.array([1,-1,1],np.float32),IM[i],mask=M[i],tri=True,return_indices=False)
        V.append(vv*np.array([1,-1,1],np.float32));C.append((cc*255).astype(np.uint8));F.append(f+off);off+=len(vv)
    V=np.concatenate(V).astype(np.float32);C=np.concatenate(C);F=np.concatenate(F).astype(np.uint32)
    c=V.mean(0);s=np.percentile(np.linalg.norm(V-c,axis=1),95)
    ((V-c)/s).astype(np.float32).tofile(f"compare/bin/{tag}.pos")
    C.tofile(f"compare/bin/{tag}.col");F.tofile(f"compare/bin/{tag}.idx")
    print(f"  {tag}: 顶点{len(V)/1e6:.2f}M 面{len(F)/1e6:.2f}M",flush=True)
# ---- 大批:从已存的 132 结果里取
z=np.load("dpk_unposed.npz")
IMall=np.stack([np.clip(v["img"][0].permute(1,2,0).numpy()*STD+MEAN,0,1) for v in load_images([files[i] for i in SEL])])
emit("big8", z["D"].astype(np.float32)[SEL], z["M"][SEL], z["K"][SEL], z["P"][SEL], IMall)
# ---- 小批:只喂这 8 张
m=wrap(MapAnything.from_pretrained("weights/v1").to("mps").eval(),8)
views=load_images([files[i] for i in SEL])
t=time.time()
with torch.inference_mode():
    outs=m.infer(views,memory_efficient_inference=True,minibatch_size=1,use_amp=True,
                 amp_dtype="bf16",apply_mask=True,mask_edges=True)
print(f"  单独 8 张 {time.time()-t:.0f}s",flush=True)
emit("small8", np.stack([o["depth_z"][0].squeeze(-1).float().cpu().numpy() for o in outs]),
     np.stack([o["mask"][0].squeeze(-1).cpu().numpy().astype(bool) for o in outs]),
     np.stack([o["intrinsics"][0].float().cpu().numpy() for o in outs]),
     np.stack([o["camera_poses"][0].float().cpu().numpy() for o in outs]), IMall)
