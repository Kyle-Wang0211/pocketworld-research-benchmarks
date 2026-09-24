#!/usr/bin/env python3
# [2026-09-24] VGGT's own output, exactly as its official Gradio demo produces it (facebookresearch/vggt @a288dd0):
#   demo_gradio.py run_model() (copied verbatim below) -> visual_util.predictions_to_glb() with the demo UI defaults
#   (demo_gradio.py:466-480: prediction_mode "Depthmap and Camera Branch", conf_thres slider 50, frame "All",
#    show_cam True, mask_sky/black/white False).
# No TSDF, no alignment to our cameras, no filtering of ours. Only forced difference: weights = the local
# VGGT-1B-Commercial model.safetensors (the demo downloads the non-commercial VGGT-1B model.pt, demo_gradio.py:33-34).
# Also exported at conf_thres=0 (the slider's minimum) = every predicted point.
import sys, os, glob, time, json
import numpy as np
import torch
from safetensors.torch import load_file
sys.path.insert(0, "/root/vggt_eval/vggt")
from vggt.models.vggt import VGGT
from vggt.utils.load_fn import load_and_preprocess_images
from vggt.utils.pose_enc import pose_encoding_to_extri_intri
from vggt.utils.geometry import unproject_depth_map_to_point_map
from visual_util import predictions_to_glb

TARGET = "/root/vggt_eval/demo_official"
OUT = "/root/page_cmp/vggt_raw"


def run_model(target_dir, model) -> dict:   # verbatim from demo_gradio.py:44-99
    """
    Run the VGGT model on images in the 'target_dir/images' folder and return predictions.
    """
    print(f"Processing images from {target_dir}")

    # Device check
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if not torch.cuda.is_available():
        raise ValueError("CUDA is not available. Check your environment.")

    # Move model to device
    model = model.to(device)
    model.eval()

    # Load and preprocess images
    image_names = glob.glob(os.path.join(target_dir, "images", "*"))
    image_names = sorted(image_names)
    print(f"Found {len(image_names)} images")
    if len(image_names) == 0:
        raise ValueError("No images found. Check your upload.")

    images = load_and_preprocess_images(image_names).to(device)
    print(f"Preprocessed images shape: {images.shape}")

    # Run inference
    print("Running inference...")
    dtype = torch.bfloat16 if torch.cuda.get_device_capability()[0] >= 8 else torch.float16

    with torch.no_grad():
        with torch.cuda.amp.autocast(dtype=dtype):
            predictions = model(images)

    # Convert pose encoding to extrinsic and intrinsic matrices
    print("Converting pose encoding to extrinsic and intrinsic matrices...")
    extrinsic, intrinsic = pose_encoding_to_extri_intri(predictions["pose_enc"], images.shape[-2:])
    predictions["extrinsic"] = extrinsic
    predictions["intrinsic"] = intrinsic

    # Convert tensors to numpy
    for key in predictions.keys():
        if isinstance(predictions[key], torch.Tensor):
            predictions[key] = predictions[key].cpu().numpy().squeeze(0)  # remove batch dimension
    predictions['pose_enc_list'] = None # remove pose_enc_list

    # Generate world points from depth map
    print("Computing world points from depth map...")
    depth_map = predictions["depth"]  # (S, H, W, 1)
    world_points = unproject_depth_map_to_point_map(depth_map, predictions["extrinsic"], predictions["intrinsic"])
    predictions["world_points_from_depth"] = world_points

    # Clean up
    torch.cuda.empty_cache()
    return predictions


os.makedirs(f"{TARGET}/images", exist_ok=True)
os.makedirs(OUT, exist_ok=True)
for p in sorted(glob.glob("/root/mvs_P16k/images/*.jpg")):          # the same 132 full-res photos
    d = f"{TARGET}/images/{os.path.basename(p)}"
    if not os.path.exists(d):
        os.symlink(p, d)

t0 = time.time()
model = VGGT()
model.load_state_dict(load_file("/root/vggt_eval/weights/VGGT-1B-Commercial/model.safetensors"))
print(f"model loaded {time.time()-t0:.0f}s", flush=True)
torch.cuda.reset_peak_memory_stats(); torch.cuda.synchronize(); t1 = time.time()
predictions = run_model(TARGET, model)
torch.cuda.synchronize(); t_run = time.time() - t1; peak = torch.cuda.max_memory_allocated() / 1e9
print(f"run_model: {t_run:.1f}s (incl. image loading), peak GPU {peak:.1f} GB", flush=True)

info = {"run_model_s": round(t_run, 1), "peak_gpu_gb": round(peak, 1),
        "images_shape": list(predictions["images"].shape), "glb": {}}
for tag, thr in (("demo_default_conf50", 50.0), ("all_points_conf0", 0.0)):
    scene = predictions_to_glb(predictions, conf_thres=thr, filter_by_frames="All", mask_black_bg=False,
                               mask_white_bg=False, show_cam=True, mask_sky=False, target_dir=TARGET,
                               prediction_mode="Depthmap and Camera Branch")
    f = f"{OUT}/{tag}.glb"
    scene.export(file_obj=f)
    npts = sum(len(g.vertices) for g in scene.geometry.values() if g.__class__.__name__ == "PointCloud")
    info["glb"][tag] = {"conf_thres_pct": thr, "points": int(npts), "bytes": os.path.getsize(f)}
    print(tag, info["glb"][tag], flush=True)
S, H, W = predictions["depth_conf"].shape[:3]
info["total_pixels"] = int(S * H * W)
json.dump(info, open(f"{OUT}/info.json", "w"), indent=1)
print(json.dumps(info, indent=1))
print("VGGT_DEMO_DONE")
