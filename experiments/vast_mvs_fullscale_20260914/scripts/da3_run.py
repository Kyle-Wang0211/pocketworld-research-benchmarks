#!/usr/bin/env python3
"""DA3-BASE pose-conditioned 多视图,喂我们已有的 COLMAP 位姿。
   extrinsics/intrinsics 直接取自 MVSNet 约定的 *_cam.txt(1-5 行 = world-to-camera 4x4, 7-10 行 = K)。
   官方 API 原样调用,不自写融合。 用法: da3_run.py <n_views> <out_dir> [model]"""
import sys, os, glob, time
import numpy as np, torch
N = int(sys.argv[1]); OUT = sys.argv[2]
MODEL = sys.argv[3] if len(sys.argv) > 3 else "depth-anything/DA3-BASE"
SRC = "/root/off768_true"
os.makedirs(OUT, exist_ok=True)
cams = sorted(glob.glob(f"{SRC}/cams/*_cam.txt"))
idx = np.linspace(0, len(cams)-1, N).astype(int) if N < len(cams) else np.arange(len(cams))
E = []; K = []; imgs = []
for i in idx:
    L = [l.rstrip() for l in open(cams[i])]
    E.append(np.fromstring(" ".join(L[1:5]), sep=" ").reshape(4,4))
    K.append(np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3,3))
    n = os.path.basename(cams[i])[:8]
    p = f"{SRC}/images/{n}.jpg"
    if not os.path.exists(p): p = f"{SRC}/images/{n}.png"
    imgs.append(p)
E = np.stack(E).astype(np.float32); K = np.stack(K).astype(np.float32)
print(f"{len(imgs)} 视图  E{E.shape} K{K.shape}", flush=True)
print("  自证 K[0]:", np.round(K[0],2).tolist(), flush=True)
from depth_anything_3.api import DepthAnything3
t0=time.time(); model = DepthAnything3.from_pretrained(MODEL).to("cuda")
print(f"  载入 {time.time()-t0:.1f}s  参数 {sum(p.numel() for p in model.parameters())/1e6:.1f}M", flush=True)
t0=time.time()
pred = model.inference(image=imgs, extrinsics=E, intrinsics=K,
                       export_dir=OUT, export_format="npz", process_res=int(os.environ.get("PROC_RES","504")),
                       num_max_points=int(os.environ.get("MAXPTS","50000000")))
print(f"  推理 {time.time()-t0:.1f}s", flush=True)
print("  产物:", sorted(os.listdir(OUT))[:8], flush=True)
print("  显存峰值 %.1f GB" % (torch.cuda.max_memory_allocated()/2**30), flush=True)
