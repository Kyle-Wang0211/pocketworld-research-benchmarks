#!/usr/bin/env python3
"""MapAnything inference with KNOWN COLMAP intrinsics + poses (the mode measured on 09-03 to follow the given pose),
exporting one depth map per view in that view's camera frame — the input the visibility graph cut needs.
Nothing is anchored, gated or upsampled here: these are MapAnything's raw depths, the version with the MOST
cross-view disagreement, so a graph cut that collapses them is proving the mechanism on the hardest case."""
import sys, os, glob, json, numpy as np, torch, cv2
sys.path.insert(0, "/root/map-anything")
from mapanything.models import MapAnything
SRC, OUT = sys.argv[1], sys.argv[2]
os.makedirs(OUT, exist_ok=True)
def read_cam(p):
    L = [l.rstrip() for l in open(p)]
    return (np.fromstring(" ".join(L[1:5]), sep=" ").reshape(4, 4).astype(np.float32),
            np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3, 3).astype(np.float32))
cams = sorted(glob.glob(f"{SRC}/cams/*_cam.txt"))
views = []
for p in cams:
    i = int(os.path.basename(p)[:8]); E, K = read_cam(p)
    img = cv2.imread(f"{SRC}/images/{i:08d}.jpg")[:, :, ::-1].astype(np.float32) / 255.0
    h, w = img.shape[:2]
    c2w = np.linalg.inv(E)
    views.append({"idx": i,
                  "img": torch.from_numpy(np.ascontiguousarray(img.transpose(2, 0, 1)))[None],
                  "intrinsics": torch.from_numpy(K)[None],
                  "camera_poses": torch.from_numpy(c2w.astype(np.float32))[None],
                  "is_metric_scale": torch.tensor([True])})
print("views", len(views), "image", views[0]["img"].shape, flush=True)
model = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda").eval()
batch = [{k: (v.to("cuda") if torch.is_tensor(v) else v) for k, v in vw.items() if k != "idx"} for vw in views]
with torch.no_grad():
    preds = model.infer(batch, memory_efficient_inference=True,
                        use_amp=True, amp_dtype="bf16",
                        apply_mask=True, mask_edges=True,
                        apply_confidence_mask=False,
                        controlled_inference_dtype=None) if hasattr(model, "infer") else None
print("pred keys", list(preds[0].keys()), flush=True)
n = 0
for vw, pr in zip(views, preds):
    d = pr["depth_z"].squeeze().float().cpu().numpy()
    m = pr["mask"].squeeze().cpu().numpy().astype(bool) if "mask" in pr else (d > 0)
    np.save(f"{OUT}/{vw['idx']:08d}_depth.npy", np.where(m, d, 0).astype(np.float32)); n += 1
print("saved", n, "depth maps to", OUT, flush=True)
