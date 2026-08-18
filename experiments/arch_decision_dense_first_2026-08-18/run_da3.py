# DA3 分离度探针 - 步骤2: 对墙区源帧跑 DA3METRIC-LARGE (MPS, 单帧串行)
# 输出 canonical 深度(需 ×f_proc/300 转米), 存 npz
import os, sys, time, json
import numpy as np

SC = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/944d5894-a2f9-49d6-bf99-1527dc18a26d/scratchpad"
OUT = SC + "/da3probe"
BASE = "/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818"
MODEL = "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3METRIC-LARGE"
FRAMES = [78, 79, 80, 81, 82, 83, 85, 86, 87, 100, 103, 107, 125]
PROC_RES = 504

import torch
from depth_anything_3.api import DepthAnything3

t0 = time.time()
model = DepthAnything3.from_pretrained(MODEL)
model = model.to("mps")
model.device = torch.device("mps")
print(f"model loaded {time.time()-t0:.1f}s; name={model.model_name}", flush=True)

meta = {}
for fr in FRAMES:
    img = f"{BASE}/in_P16k/images/frame_{fr:06d}.jpg"
    t1 = time.time()
    pred = model.inference([img], process_res=PROC_RES, process_res_method="upper_bound_resize")
    dt = time.time() - t1
    depth = pred.depth[0].astype(np.float32)          # canonical
    conf = pred.conf[0].astype(np.float32) if pred.conf is not None else None
    kw = dict(depth=depth)
    if conf is not None:
        kw["conf"] = conf
    np.savez_compressed(f"{OUT}/da3_{fr}.npz", **kw)
    im_flag = pred.is_metric if isinstance(pred.is_metric, (int, float, bool)) else -1
    meta[fr] = dict(shape=list(depth.shape), sec=round(dt, 3),
                    is_metric=int(im_flag),
                    d_min=float(depth.min()), d_med=float(np.median(depth)), d_max=float(depth.max()))
    print(fr, json.dumps(meta[fr]), flush=True)

json.dump(meta, open(OUT + "/da3_meta.json", "w"), indent=1)
print("ALL OK", flush=True)
