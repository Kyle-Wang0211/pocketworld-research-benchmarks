#!/usr/bin/env python3
"""Colorize a replay cloud with decode long-edge capped at <maxside> px
(0 = full resolution). Same certified recipe otherwise (track obs, bilinear,
mean, round). Device semantics: ImageIO DCT downscale ~= PIL BILINEAR resize.
Usage: colorize_at_res.py <run_dir> <fed_jsonl> <photos_dir> <maxside> <out_ply>
"""
import json, os, struct, sys
import numpy as np
from PIL import Image

run_dir, fed_path, photos_dir, maxside, out_ply = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]

fed = {}
with open(fed_path) as fh:
    for line in fh:
        j = json.loads(line)
        fed[j["frameId"]] = (os.path.basename(j["jpegPath"]), j["grayW"], j["grayH"])

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

req = {}
for pi, tr in enumerate(tracks):
    for iid, p2 in tr:
        req.setdefault(int(iid), []).append((pi, int(p2)))

acc = np.zeros((n_pts, 3)); cnt = np.zeros(n_pts, np.int64)
miss = 0
for iid in sorted(req):
    name, xy = images[iid]
    fid = int(os.path.splitext(name)[0])
    if fid not in fed:
        miss += 1; continue
    base, gw, gh = fed[fid]
    path = os.path.join(photos_dir, base)
    if not os.path.exists(path):
        miss += 1; continue
    pil = Image.open(path).convert("RGB")
    W, H = pil.size
    if maxside > 0 and max(W, H) > maxside:
        s = maxside / max(W, H)
        pil = pil.resize((max(1, round(W * s)), max(1, round(H * s))), Image.BILINEAR)
    im = np.asarray(pil)
    h, w = im.shape[:2]
    sx, sy = w / gw, h / gh
    for pi, p2 in req[iid]:
        x, y = xy[p2, 0] * sx, xy[p2, 1] * sy
        x0 = min(max(int(np.floor(x)), 0), w - 2); y0 = min(max(int(np.floor(y)), 0), h - 2)
        x = min(max(x, 0), w - 1.0); y = min(max(y, 0), h - 1.0)
        fx, fy = x - x0, y - y0
        c = (im[y0, x0] * (1-fx) * (1-fy) + im[y0, x0+1] * fx * (1-fy)
             + im[y0+1, x0] * (1-fx) * fy + im[y0+1, x0+1] * fx * fy)
        acc[pi] += c; cnt[pi] += 1

rgb = np.full((n_pts, 3), 128, np.uint8)
ok = cnt > 0
rgb[ok] = np.clip(np.round(acc[ok] / cnt[ok, None]), 0, 255).astype(np.uint8)
with open(out_ply, "wb") as f:
    f.write(b"ply\nformat binary_little_endian 1.0\n")
    f.write(f"comment colorize decode maxside={maxside or 'full'}\n".encode())
    f.write(f"element vertex {n_pts}\n".encode())
    f.write(b"property float x\nproperty float y\nproperty float z\n")
    f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    buf = np.zeros(n_pts, dtype=[("xyz", "<f4", 3), ("rgb", "u1", 3)])
    buf["xyz"] = pts.astype(np.float32); buf["rgb"] = rgb
    f.write(buf.tobytes())
print(f"{out_ply}: n={n_pts} colored={int(ok.sum())} gray={int((~ok).sum())} maxside={maxside or 'full'} miss={miss}")
