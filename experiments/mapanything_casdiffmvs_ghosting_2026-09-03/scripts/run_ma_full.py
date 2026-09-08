#!/usr/bin/env python3
"""Re-run MapAnything exactly as run_ma_depths.py did, but ALSO save the self-predicted intrinsics
and camera poses -- those are what the anchoring step needs and what the previous run threw away."""
import sys, os, glob, numpy as np, torch, cv2
sys.path.insert(0, "/root/map-anything")
from mapanything.models import MapAnything
from mapanything.utils.image import preprocess_inputs

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
    img = cv2.imread(f"{SRC}/images/{i:08d}.jpg")[:, :, ::-1].copy()
    c2w = np.linalg.inv(E).astype(np.float32)
    views.append({"idx": i, "img": torch.from_numpy(img), "intrinsics": torch.from_numpy(K),
                  "camera_poses": torch.from_numpy(c2w), "is_metric_scale": torch.tensor([True])})
print("views", len(views), "image", views[0]["img"].shape, flush=True)

model = MapAnything.from_pretrained("facebook/map-anything-apache").to("cuda").eval()
raw = [{k: v for k, v in vw.items() if k != "idx"} for vw in views]
batch = preprocess_inputs(raw, verbose=False)
batch = [{k: (v.to("cuda") if torch.is_tensor(v) else v) for k, v in b.items()} for b in batch]
with torch.no_grad():
    preds = model.infer(batch, memory_efficient_inference=True, use_amp=True, amp_dtype="bf16",
                        apply_mask=True, mask_edges=True, apply_confidence_mask=False)

n = 0
for vw, pr in zip(views, preds):
    idx = vw["idx"]
    d = pr["depth_z"].squeeze().float().cpu().numpy()
    m = pr["mask"].squeeze().cpu().numpy().astype(bool) if "mask" in pr else (d > 0)
    Kma = pr["intrinsics"].squeeze().float().cpu().numpy()
    Pma = pr["camera_poses"].squeeze().float().cpu().numpy()
    cf = pr["conf"].squeeze().float().cpu().numpy() if "conf" in pr else np.zeros_like(d)
    np.savez(f"{OUT}/{idx:08d}.npz",
             depth_z=np.where(m, d, 0).astype(np.float32), mask=m,
             K_ma=Kma.astype(np.float32), pose_ma=Pma.astype(np.float32), conf=cf.astype(np.float32))
    n += 1
print("saved", n, "to", OUT, flush=True)
z = np.load(f"{OUT}/{views[0]['idx']:08d}.npz")
print("depth shape", z["depth_z"].shape, "K_ma:", z["K_ma"].tolist(), flush=True)
