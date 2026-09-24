#!/usr/bin/env python3
# [2026-09-24] VGGT-1B-Commercial on the 132 full-res photos, following the official export path
# facebookresearch/vggt demo_colmap.py @a288dd0 (no-BA branch):
#   load_and_preprocess_images_square(paths, 1024) -> run_VGGT(..., 518) -> unproject_depth_map_to_point_map
#   -> keep depth_conf >= 5.0 (demo_colmap.py:60,212)
# Differences, both forced: (1) weights = local VGGT-1B-Commercial model.safetensors (the demo downloads the
# non-commercial VGGT-1B model.pt); (2) pixels in the square padding (outside original_coords) are dropped, since they
# are not scene pixels. The demo's random 100k-point cap only limits the COLMAP export size and is not applied.
import sys, time, json
import numpy as np
import torch
import torch.nn.functional as F
from safetensors.torch import load_file
sys.path.insert(0, "/root/vggt_eval/vggt")
from vggt.models.vggt import VGGT
from vggt.utils.load_fn import load_and_preprocess_images_square
from vggt.utils.pose_enc import pose_encoding_to_extri_intri
from vggt.utils.geometry import unproject_depth_map_to_point_map


def run_VGGT(model, images, dtype, resolution=518):   # verbatim from demo_colmap.py:65-91
    assert len(images.shape) == 4
    assert images.shape[1] == 3
    images = F.interpolate(images, size=(resolution, resolution), mode="bilinear", align_corners=False)
    with torch.no_grad():
        with torch.cuda.amp.autocast(dtype=dtype):
            images = images[None]
            aggregated_tokens_list, ps_idx = model.aggregator(images)
        pose_enc = model.camera_head(aggregated_tokens_list)[-1]
        extrinsic, intrinsic = pose_encoding_to_extri_intri(pose_enc, images.shape[-2:])
        depth_map, depth_conf = model.depth_head(aggregated_tokens_list, images, ps_idx)
    extrinsic = extrinsic.squeeze(0).cpu().numpy()
    intrinsic = intrinsic.squeeze(0).cpu().numpy()
    depth_map = depth_map.squeeze(0).cpu().numpy()
    depth_conf = depth_conf.squeeze(0).cpu().numpy()
    return extrinsic, intrinsic, depth_map, depth_conf


order = json.load(open("/root/tsdf_improve/four/cache/order.json"))["order"]
paths = [f"/root/mvs_P16k/images/{v:08d}.jpg" for v in order]
dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16
t0 = time.time()
model = VGGT()
model.load_state_dict(load_file("/root/vggt_eval/weights/VGGT-1B-Commercial/model.safetensors"))
model.eval().to("cuda")
print(f"model loaded ({sum(p.numel() for p in model.parameters()):,} params) {time.time()-t0:.0f}s", flush=True)
images, original_coords = load_and_preprocess_images_square(paths, 1024)
images = images.to("cuda")
print(f"images {tuple(images.shape)}  {time.time()-t0:.0f}s", flush=True)
torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize(); t1 = time.time()
extrinsic, intrinsic, depth_map, depth_conf = run_VGGT(model, images, dtype, 518)
torch.cuda.synchronize(); t_inf = time.time() - t1; peak = torch.cuda.max_memory_allocated() / 1e9
print(f"VGGT forward on {len(paths)} frames: {t_inf:.1f}s, peak GPU memory {peak:.1f} GB", flush=True)
points_3d = unproject_depth_map_to_point_map(depth_map, extrinsic, intrinsic)   # (N,518,518,3), VGGT world frame
N, H, W = depth_conf.shape[:3]
oc = original_coords.cpu().numpy() * (518.0 / 1024.0)                         # [x1,y1,x2,y2,...] -> 518 grid
yy, xx = np.mgrid[0:H, 0:W]
inside = np.stack([(xx >= oc[i, 0]) & (xx < oc[i, 2]) & (yy >= oc[i, 1]) & (yy < oc[i, 3]) for i in range(N)])
conf = depth_conf.reshape(N, H, W)
keep = inside & (conf >= 5.0)
print(f"pixels inside original image {inside.sum():,}; with conf>=5.0 {keep.sum():,} ({100*keep.sum()/inside.sum():.1f}%)", flush=True)
np.savez("/root/vggt_eval/vggt_pred.npz", order=np.array(order), extrinsic=extrinsic, intrinsic=intrinsic,
         depth=depth_map.reshape(N, H, W).astype(np.float32), conf=conf.astype(np.float32), inside=inside, keep=keep,
         points=points_3d.astype(np.float32), forward_s=t_inf, peak_gb=peak)
print(f"saved /root/vggt_eval/vggt_pred.npz  total {time.time()-t0:.0f}s")
