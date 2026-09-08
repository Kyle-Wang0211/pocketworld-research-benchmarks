import sys, os, glob, time
sys.path.insert(0, "/root/regionmerge/Prior-Depth-Anything")
import numpy as np, torch
from prior_depth_anything import PriorDepthAnything

OUT = "/root/regionmerge/pda_out/depth_npy"
os.makedirs(OUT, exist_ok=True)
LIMIT = int(os.environ.get("LIMIT", "0"))

priorda = PriorDepthAnything(device="cuda:0")   # repo defaults: version 1.1, vitb/vitb, K=5
imgs = sorted(glob.glob("/root/regionmerge/rgb768/*.jpg"))
if LIMIT: imgs = imgs[:LIMIT]
t0 = time.time()
for i, ip in enumerate(imgs):
    stem = os.path.splitext(os.path.basename(ip))[0]
    pp = f"/root/regionmerge/prior_npy/{stem}.npy"
    out = priorda.infer_one_sample(image=ip, prior=pp, visualize=False)
    d = out.detach().squeeze().cpu().numpy().astype(np.float32)
    np.save(f"{OUT}/{stem}.npy", d)
    if i % 10 == 0:
        pr = np.load(pp); m = pr > 0
        r = d[m] / pr[m]
        print(f"[{i}/{len(imgs)}] {stem} shape={d.shape} range={d.min():.3f}-{d.max():.3f} "
              f"prior-ratio p50={np.median(r):.4f} p10={np.percentile(r,10):.4f} p90={np.percentile(r,90):.4f} "
              f"{time.time()-t0:.1f}s", flush=True)
print("DONE", len(imgs), f"{time.time()-t0:.1f}s", flush=True)
