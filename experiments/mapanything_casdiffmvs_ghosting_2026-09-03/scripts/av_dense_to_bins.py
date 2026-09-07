#!/usr/bin/env python3
"""AliceVision's own filtered depth maps -> full-resolution coloured point cloud in OUR world frame, then viewer
bins. This is AliceVision's result end to end (its depths, its filtering); we only back-project and change frame.
AliceVision depth = distance along the ray, world = ours with y,z negated (both verified earlier)."""
import sys, json, glob, os, numpy as np, cv2, OpenEXR
MESH, FILT, SFM, OUT, TAG = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
os.makedirs(OUT, exist_ok=True)
d = json.load(open(SFM))
vid2name = {v["viewId"]: v["path"].rsplit("/", 1)[-1] for v in d["views"]}
def read_cam(i):
    L = [l.rstrip() for l in open(f"/root/out_official/cams/{i:08d}_cam.txt")]
    return (np.fromstring(" ".join(L[1:5]), sep=" ").reshape(4, 4),
            np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3, 3))
P = []; C = []
for f in sorted(glob.glob(f"{FILT}/*_depthMap.exr")):
    vid = os.path.basename(f).split("_")[0]
    if vid not in vid2name: continue
    i = int(vid2name[vid][:8])
    with OpenEXR.File(f) as ex:
        ch = ex.channels(); key = "Y" if "Y" in ch else list(ch)[0]
        dist = np.asarray(ch[key].pixels).astype(np.float32)
    h, w = dist.shape
    E, K = read_cam(i)
    sx = w / 768.0; sy = h / 576.0
    Ks = K.copy(); Ks[0, :] *= sx; Ks[1, :] *= sy
    img = cv2.imread(f"/root/out_official/images/{i:08d}.jpg")
    if img.shape[:2] != (h, w): img = cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)
    u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    ray = np.sqrt(((u - Ks[0, 2]) / Ks[0, 0]) ** 2 + ((v - Ks[1, 2]) / Ks[1, 1]) ** 2 + 1.0)
    ok = dist > 0
    Z = np.where(ok, dist / ray, 0.0)
    x = (u[ok] - Ks[0, 2]) / Ks[0, 0] * Z[ok]; y = (v[ok] - Ks[1, 2]) / Ks[1, 1] * Z[ok]
    Xc = np.stack([x, y, Z[ok], np.ones_like(x)], 0)
    Xw = (np.linalg.inv(E) @ Xc)[:3].T
    P.append(Xw.astype(np.float32)); C.append(img[ok][:, ::-1].astype(np.uint8))
P = np.concatenate(P); C = np.concatenate(C)
print("AliceVision dense cloud:", len(P), "points from", len(glob.glob(f'{FILT}/*_depthMap.exr')), "filtered maps", flush=True)
pos = P.copy(); pos[:, 1] *= -1; pos[:, 2] *= -1
pos = np.ascontiguousarray(pos.astype("<f4")); col = np.ascontiguousarray(C)
pos.tofile(f"{OUT}/{TAG}.pos"); col.tofile(f"{OUT}/{TAG}.col")
lo, hi = np.percentile(pos, 1, 0), np.percentile(pos, 99, 0); med = np.median(pos, 0)
rad = float(np.percentile(np.linalg.norm(pos - med, axis=1), 95))
json.dump({TAG: {"n": int(len(pos)), "center": ((lo + hi) / 2).tolist(), "ext": (hi - lo).tolist(),
                 "med": med.astype(float).tolist(), "radius": rad}}, open(f"{OUT}/meta_{TAG}.json", "w"))
print("wrote", TAG, len(pos), "med", np.round(med, 3).tolist(), flush=True)
