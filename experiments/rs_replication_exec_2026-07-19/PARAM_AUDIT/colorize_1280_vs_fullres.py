#!/usr/bin/env python3
"""D#12 定价:取色解码 1280px(设备现状,来路=07-09 streaming 沿用,无签决)
vs 全分辨率(认证 'o' 口径)。同 track 同观测同配方,唯一变量=解码分辨率。
设备语义仿真:ImageIO 长边 1280 降采样 ~= PIL BILINEAR resize;kp 坐标按比例缩放。
尺:每点 ΔRGB(L∞)分布 + 超阈值点占比(8/16/32 级);按局部色彩梯度分层(边缘 vs 平坦)。
Usage: colorize_1280_vs_fullres.py <run_dir> <fed_jsonl> <photos_dir> <out_json>
"""
import json, os, struct, sys
import numpy as np
from PIL import Image

run_dir, fed_path, photos_dir, out_json = sys.argv[1:5]

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

pts_track = []
with open(f"{run_dir}/points3D.bin", "rb") as f:
    n_pts = struct.unpack("<Q", f.read(8))[0]
    for _ in range(n_pts):
        f.read(8 + 24 + 3 + 8)
        tl = struct.unpack("<Q", f.read(8))[0]
        tr = np.frombuffer(f.read(tl * 8), dtype=np.uint32).reshape(tl, 2)
        pts_track.append(tr.copy())

req = {}
for pi, tr in enumerate(pts_track):
    for iid, p2 in tr:
        req.setdefault(int(iid), []).append((pi, int(p2)))

acc = {k: np.zeros((n_pts, 3)) for k in ("full", "lo")}
cnt = np.zeros(n_pts, np.int64)
grad_max = np.zeros(n_pts)  # full-res local gradient proxy at obs, max over obs

def bilin(im, x, y):
    h, w = im.shape[:2]
    x0 = min(max(int(np.floor(x)), 0), w - 2); y0 = min(max(int(np.floor(y)), 0), h - 2)
    x = min(max(x, 0), w - 1.0); y = min(max(y, 0), h - 1.0)
    fx, fy = x - x0, y - y0
    return (im[y0, x0] * (1-fx) * (1-fy) + im[y0, x0+1] * fx * (1-fy)
            + im[y0+1, x0] * (1-fx) * fy + im[y0+1, x0+1] * fx * fy)

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
    im_full = np.asarray(pil)
    scale = 1280.0 / max(W, H)
    lw, lh = max(1, round(W * scale)), max(1, round(H * scale))
    im_lo = np.asarray(pil.resize((lw, lh), Image.BILINEAR))
    sxf, syf = W / gw, H / gh
    sxl, syl = lw / gw, lh / gh
    for pi, p2 in req[iid]:
        kx, ky = xy[p2, 0], xy[p2, 1]
        cf = bilin(im_full, kx * sxf, ky * syf)
        cl = bilin(im_lo, kx * sxl, ky * syl)
        acc["full"][pi] += cf; acc["lo"][pi] += cl; cnt[pi] += 1
        gx = abs(float(bilin(im_full, min(kx*sxf+3, W-1.0), ky*syf).mean()) - float(bilin(im_full, max(kx*sxf-3, 0.0), ky*syf).mean()))
        gy = abs(float(bilin(im_full, kx*sxf, min(ky*syf+3, H-1.0)).mean()) - float(bilin(im_full, kx*sxf, max(ky*syf-3, 0.0)).mean()))
        grad_max[pi] = max(grad_max[pi], gx, gy)

ok = cnt > 0
rgb_full = np.clip(np.round(acc["full"][ok] / cnt[ok, None]), 0, 255)
rgb_lo = np.clip(np.round(acc["lo"][ok] / cnt[ok, None]), 0, 255)
d = np.abs(rgb_full - rgb_lo).max(1)
g = grad_max[ok]
edge = g > 24  # full-res local contrast > ~24/255 within +-3px => edge-ish
rep = {
    "n_points_colored": int(ok.sum()), "frames_missing_photo": miss,
    "delta_Linf": {"p50": float(np.percentile(d, 50)), "p90": float(np.percentile(d, 90)),
                    "p99": float(np.percentile(d, 99)), "max": float(d.max())},
    "pct_gt8": round(float((d > 8).mean()) * 100, 2),
    "pct_gt16": round(float((d > 16).mean()) * 100, 2),
    "pct_gt32": round(float((d > 32).mean()) * 100, 2),
    "edge_stratum": {"n": int(edge.sum()),
                      "pct_gt16": round(float((d[edge] > 16).mean()) * 100, 2) if edge.any() else None,
                      "pct_gt32": round(float((d[edge] > 32).mean()) * 100, 2) if edge.any() else None},
    "flat_stratum": {"n": int((~edge).sum()),
                      "pct_gt16": round(float((d[~edge] > 16).mean()) * 100, 2) if (~edge).any() else None},
    "semantics": "delta = Linf per-point RGB, certified fullres bilinear-mean-round vs device 1280px decode; edge = fullres local contrast>24 within +-3px at any obs",
}
json.dump(rep, open(out_json, "w"), indent=1)
print(json.dumps(rep, indent=1))
