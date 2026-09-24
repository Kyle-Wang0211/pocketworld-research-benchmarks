#!/usr/bin/env python3
# [2026-09-24] MapAnything (Apache-2.0 checkpoint) fed our known intrinsics + poses, following the official script
# facebookresearch/map-anything scripts/demo_inference_on_colmap_outputs.py @3d10cf7 main(): load_colmap_data ->
# preprocess_inputs -> model.infer(same arguments as the script) -> depthmap_to_world_frame + pred mask.
# Only differences: weights loaded from the local copy of facebook/map-anything-apache (= the script's --apache), and
# per-view outputs are saved to .npz instead of rerun/GLB.
import os, sys, time, importlib.util
import numpy as np, torch
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
from mapanything.models import MapAnything
from mapanything.utils.image import preprocess_inputs
from mapanything.utils.geometry import depthmap_to_world_frame
spec = importlib.util.spec_from_file_location("demo", "/root/mapany_eval/map-anything/scripts/demo_inference_on_colmap_outputs.py")
demo = importlib.util.module_from_spec(spec); spec.loader.exec_module(demo)          # reuse its load_colmap_data verbatim
t0 = time.time()
model = MapAnything.from_pretrained("/root/mapany_eval/weights/map-anything-apache").to("cuda")
views_example, image_names = demo.load_colmap_data("/root/mapany_eval/scene", stride=1, verbose=False, ext=".bin")
print(f"loaded {len(views_example)} views {time.time()-t0:.0f}s", flush=True)
processed_views = preprocess_inputs(views_example, verbose=False)
torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize(); t1 = time.time()
outputs = model.infer(processed_views, memory_efficient_inference=True, minibatch_size=1,
                      ignore_calibration_inputs=False, ignore_depth_inputs=True, ignore_pose_inputs=False,
                      ignore_depth_scale_inputs=True, ignore_pose_scale_inputs=True,
                      use_amp=True, amp_dtype="bf16", apply_mask=True, mask_edges=True)
torch.cuda.synchronize(); tinf = time.time() - t1; peak = torch.cuda.max_memory_allocated() / 1e9
print(f"infer {len(outputs)} views: {tinf:.1f}s, peak GPU {peak:.1f} GB", flush=True)
pts, masks, poses, Ks, confs = [], [], [], [], []
for pred in outputs:
    depthmap_torch = pred["depth_z"][0].squeeze(-1); intrinsics_torch = pred["intrinsics"][0]; camera_pose_torch = pred["camera_poses"][0]
    pts3d_computed, valid_mask = depthmap_to_world_frame(depthmap_torch, intrinsics_torch, camera_pose_torch)
    mask = pred["mask"][0].squeeze(-1).cpu().numpy().astype(bool) & valid_mask.cpu().numpy()
    pts.append(pts3d_computed.cpu().numpy().astype(np.float32)); masks.append(mask)
    poses.append(camera_pose_torch.cpu().numpy()); Ks.append(intrinsics_torch.cpu().numpy()); confs.append(pred["conf"][0].float().cpu().numpy())
masks = np.stack(masks)
print(f"output res {pts[0].shape[:2]}, masked-in pixels {masks.sum():,} / {masks.size:,} ({100*masks.mean():.1f}%)", flush=True)
np.savez("/root/mapany_eval/mapany_pred.npz", names=np.array(image_names), pts=np.stack(pts), mask=masks, poses=np.stack(poses),
         K=np.stack(Ks), conf=np.stack(confs), infer_s=tinf, peak_gb=peak)
print(f"saved  total {time.time()-t0:.0f}s")
