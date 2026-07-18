#!/usr/bin/env python3
"""Colorize replay points3D.bin with the certified recipe:
track obs -> full-res bilinear -> mean over obs -> round. (rs_gate_sweep_v2 lineage)
Keypoint xy are in detection (gray) resolution; scaled per-frame by fed jsonl grayW/H.
Frames with no photo on disk contribute nothing; points with zero sampled obs -> gray(128).
Usage: colorize_replay.py <run_dir> <fed_jsonl> <photos_dir> <out_ply>
"""
import json, os, struct, sys
import numpy as np
from PIL import Image

run_dir, fed_path, photos_dir, out_ply = sys.argv[1:5]

fed = {}
with open(fed_path) as fh:
    for line in fh:
        j = json.loads(line)
        fed[j["frameId"]] = (os.path.basename(j["jpegPath"]), j["grayW"], j["grayH"])

# images.bin (layout validated on this vendored build: id u32, 68B fixed, cstr name, n u64, n*(x f64,y f64,p3d u64))
images = {}
with open(f"{run_dir}/images.bin", "rb") as f:
    n_img = struct.unpack("<Q", f.read(8))[0]
    for _ in range(n_img):
        iid = struct.unpack("<I", f.read(4))[0]
        f.read(68)
        name = b""
        while (c := f.read(1)) != b"\x00":
            name += c
        n2 = struct.unpack("<Q", f.read(8))[0]
        rec = np.frombuffer(f.read(n2 * 24), dtype=np.float64).reshape(n2, 3)
        images[iid] = (name.decode(), rec[:, :2].copy())

# points3D.bin
pts, tracks = [], []
with open(f"{run_dir}/points3D.bin", "rb") as f:
    n_pts = struct.unpack("<Q", f.read(8))[0]
    for _ in range(n_pts):
        f.read(8)
        pts.append(struct.unpack("<3d", f.read(24)))
        f.read(3 + 8)
        tl = struct.unpack("<Q", f.read(8))[0]
        tr = np.frombuffer(f.read(tl * 8), dtype=np.uint32).reshape(tl, 2)
        tracks.append(tr.copy())
pts = np.asarray(pts, np.float64)

req = {}  # iid -> list of (point_idx, p2d_idx)
for pi, tr in enumerate(tracks):
    for iid, p2 in tr:
        req.setdefault(int(iid), []).append((pi, int(p2)))

acc = np.zeros((n_pts, 3)); cnt = np.zeros(n_pts, np.int64)
miss_img = 0
for iid in sorted(req):
    name, xy = images[iid]
    frame_id = int(os.path.splitext(name)[0])
    if frame_id not in fed:
        miss_img += 1; continue
    base, gw, gh = fed[frame_id]
    path = os.path.join(photos_dir, base)
    if not os.path.exists(path):
        miss_img += 1; continue
    im = np.asarray(Image.open(path).convert("RGB"))
    h, w = im.shape[:2]
    sx, sy = w / gw, h / gh
    for pi, p2 in req[iid]:
        x, y = xy[p2, 0] * sx, xy[p2, 1] * sy
        x0, y0 = int(np.floor(x)), int(np.floor(y))
        x0 = min(max(x0, 0), w - 2); y0 = min(max(y0, 0), h - 2)
        x = min(max(x, 0), w - 1.0); y = min(max(y, 0), h - 1.0)
        fx, fy = x - x0, y - y0
        c = (im[y0, x0] * (1 - fx) * (1 - fy) + im[y0, x0 + 1] * fx * (1 - fy)
             + im[y0 + 1, x0] * (1 - fx) * fy + im[y0 + 1, x0 + 1] * fx * fy)
        acc[pi] += c; cnt[pi] += 1

rgb = np.full((n_pts, 3), 128, np.uint8)
ok = cnt > 0
rgb[ok] = np.clip(np.round(acc[ok] / cnt[ok, None]), 0, 255).astype(np.uint8)

with open(out_ply, "wb") as f:
    f.write(b"ply\nformat binary_little_endian 1.0\n")
    f.write(f"element vertex {n_pts}\n".encode())
    f.write(b"property float x\nproperty float y\nproperty float z\n")
    f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    buf = np.zeros(n_pts, dtype=[("xyz", "<f4", 3), ("rgb", "u1", 3)])
    buf["xyz"] = pts.astype(np.float32); buf["rgb"] = rgb
    f.write(buf.tobytes())
print(f"{out_ply}: n={n_pts} colored={int(ok.sum())} gray={int((~ok).sum())} frames_missing_photo={miss_img}")
