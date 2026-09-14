#!/usr/bin/env python3
"""让单目模型单独说话:在同样 132 张上跑 DAv2-Small 的纯单目深度。
判别用途 —— 若它自己看白墙就是歪的 ⇒ 骨干太小(差别#1);
若它看得准而 MonoMVSNet 仍粘连 ⇒ 融合机制没用上它(差别#2)。
代码走 MonoMVSNet 自带的 models/depth_anything_v2(即上游 DAv2 原版)。"""
import sys, os, glob
import numpy as np, cv2, torch
sys.path.insert(0, "/root/MonoMVSNet")
from models.depth_anything_v2.dpt import DepthAnythingV2

CFG = {"encoder": "vits", "features": 64, "out_channels": [48, 96, 192, 384]}
OUT = "/root/mono_only/dav2s"
os.makedirs(OUT, exist_ok=True)

m = DepthAnythingV2(**CFG)
sd = torch.load("/root/MonoMVSNet/pre_trained_weights/depth_anything_v2_vits.pth", map_location="cpu")
missing, unexpected = m.load_state_dict(sd, strict=False)
print(f"权重加载: missing {len(missing)} / unexpected {len(unexpected)}  (必须都是 0)")
m = m.cuda().eval()

imgs = sorted(glob.glob("/root/mvs_P16k/images/*.jpg"))
print(f"{len(imgs)} 张")
for k, p in enumerate(imgs):
    bgr = cv2.imread(p)
    bgr = cv2.resize(bgr, (1152, 832), interpolation=cv2.INTER_AREA)   # 与 MonoMVSNet 推理同分辨率
    with torch.no_grad():
        d, _ = m.infer_mono(bgr, 832, 1152, input_size=518)
        d = d.squeeze().float().cpu().numpy()
    np.save(f"{OUT}/{k:08d}.npy", d.astype(np.float32))
    if k % 40 == 0: print(f"  {k}: shape {d.shape} 范围 {d.min():.3f}~{d.max():.3f}", flush=True)
print("DONE")
