# [组大小 vs 重影 2026-08-31] 官方训练 num_views 最大 4,基准报 2。我们喂 132 = 出分布 33×。
# 量组内重影(跨组世界系不同不可比:model.py:714 每次前向以 view0 为参考系)。
import os,time,threading,resource,numpy as np,torch
from pathlib import Path
LIM=float(os.environ.get("CAP_GIB","13"))
threading.Thread(target=lambda:[(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/2**30>LIM and (print("🔴守卫",flush=True),os._exit(9)),time.sleep(0.3)) for _ in iter(int,1)],daemon=True).start()
from mapanything.models import MapAnything
from mapanything.utils.image import load_images
from minibatch_encoder import wrap
files=[str(p) for p in sorted(Path("images_rgb").glob("*"))[:132]]
m=wrap(MapAnything.from_pretrained("weights/v1").to("mps").eval(), 8)
def ghost(D,M,K,P):
    n,H,W=D.shape
    u,v=np.meshgrid(np.arange(W,dtype=np.float32),np.arange(H,dtype=np.float32))
    C=P[:,:3,3]; dist=np.linalg.norm(C[:,None]-C[None],axis=-1); np.fill_diagonal(dist,1e9)
    out=[]
    for i in range(n):
        j=int(np.argmin(dist[i])); d=D[j]; k=K[j]; p=P[j]
        x=(u-k[0,2])/k[0,0]*d; y=(v-k[1,2])/k[1,1]*d
        Wj=np.stack([x,y,d],-1)@p[:3,:3].T+p[:3,3]
        Pi=np.linalg.inv(P[i]); Cj=Wj@Pi[:3,:3].T+Pi[:3,3]; zz=Cj[...,2]
        ok=M[j]&(zz>1e-6); zs=np.where(zz==0,1,zz)
        ui=np.round(K[i][0,0]*Cj[...,0]/zs+K[i][0,2]).astype(int)
        vi=np.round(K[i][1,1]*Cj[...,1]/zs+K[i][1,2]).astype(int)
        ok&=(ui>=0)&(ui<W)&(vi>=0)&(vi<H)
        uc=np.clip(ui,0,W-1); vc=np.clip(vi,0,H-1)
        ok&=M[i][vc,uc]&(D[i][vc,uc]>1e-6)
        if ok.sum()<200: continue
        r=np.abs(zz[ok]-D[i][vc,uc][ok])/D[i][vc,uc][ok]; r=r[r<0.5]
        if r.size>200: out.append(np.median(r))
    return out
print(f"{'组大小':>6} {'组数':>5} {'耗时':>7} {'组内重影中位':>12}")
for G in (2,4,8,16,32,64,132):
    groups=[files[i:i+G] for i in range(0,132,G)]
    groups=[g for g in groups if len(g)>=2]
    allr=[]; t=time.time()
    for g in groups:
        views=load_images(g)
        with torch.inference_mode():
            outs=m.infer(views,memory_efficient_inference=True,minibatch_size=1,use_amp=True,
                         amp_dtype="bf16",apply_mask=True,mask_edges=True)
        D=np.stack([o["depth_z"][0].squeeze(-1).float().cpu().numpy() for o in outs])
        M=np.stack([o["mask"][0].squeeze(-1).cpu().numpy().astype(bool) for o in outs])
        K=np.stack([o["intrinsics"][0].float().cpu().numpy() for o in outs])
        P=np.stack([o["camera_poses"][0].float().cpu().numpy() for o in outs])
        del outs,views; torch.mps.empty_cache()
        allr+=ghost(D,M,K,P)
    print(f"{G:>6} {len(groups):>5} {time.time()-t:>6.0f}s {np.median(allr)*100:>11.2f}%",flush=True)
