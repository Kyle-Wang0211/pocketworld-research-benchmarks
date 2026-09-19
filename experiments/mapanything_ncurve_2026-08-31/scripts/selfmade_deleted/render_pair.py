# 用官方 image_mesh 建网格(与 predictions_to_glb as_mesh=True 同一函数),导出给网页看。
import numpy as np,os,struct
from pathlib import Path
from mapanything.utils.image import load_images
from mapanything.utils.hf_utils.viz import image_mesh
files=[str(p) for p in sorted(Path("images_rgb").glob("*"))[:132]]
MEAN=np.array([0.485,0.456,0.406],np.float32); STD=np.array([0.229,0.224,0.225],np.float32)
IMGS=np.stack([v["img"][0].permute(1,2,0).numpy() for v in load_images(files)])
IMGS=np.clip(IMGS*STD+MEAN,0,1)          # dinov2 归一化反算回 0..1 真彩
Path("compare/bin").mkdir(parents=True,exist_ok=True)
IDX=list(range(0,132,4))            # 33 个完整视图,两版用同一批,可比
for tag,npz in (("mvconf","dpk_mvconf.npz"),("plain","dpk_unposed.npz")):
    z=np.load(npz); D=z["D"].astype(np.float32); M=z["M"]; K=z["K"]; P=z["P"]
    n,H,W=D.shape
    u,v=np.meshgrid(np.arange(W,dtype=np.float32),np.arange(H,dtype=np.float32))
    V=[];C=[];F=[];off=0
    for i in IDX:
        d=D[i];k=K[i];p=P[i]
        x=(u-k[0,2])/k[0,0]*d; y=(v-k[1,2])/k[1,1]*d
        pts=(np.stack([x,y,d],-1)@p[:3,:3].T+p[:3,3]).astype(np.float32)
        if M[i].sum()<500: continue
        f,vv,cc=image_mesh(pts*np.array([1,-1,1],np.float32), IMGS[i],
                           mask=M[i], tri=True, return_indices=False)
        V.append(vv*np.array([1,-1,1],np.float32)); C.append((cc*255).astype(np.uint8)); F.append(f+off); off+=len(vv)
    V=np.concatenate(V).astype(np.float32); C=np.concatenate(C); F=np.concatenate(F).astype(np.uint32)
    c=V.mean(0); s=np.percentile(np.linalg.norm(V-c,axis=1),95)
    ((V-c)/s).astype(np.float32).tofile(f"compare/bin/{tag}.pos")
    C.tofile(f"compare/bin/{tag}.col"); F.tofile(f"compare/bin/{tag}.idx")
    print(f"{tag}: 视图{len(F) and len(IDX)}  顶点{len(V)/1e6:.2f}M  面{len(F)/1e6:.2f}M",flush=True)
