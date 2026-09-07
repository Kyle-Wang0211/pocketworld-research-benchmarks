#!/usr/bin/env python3.11
"""CasDiffMVS official outputs (depth_est pfm + official final mask + MVSNet cams) -> COLMAP dense workspace
(images/, sparse/*.bin, stereo/depth_maps|normal_maps/<name>.geometric.bin, stereo/fusion.cfg), so that the
official COLMAP stereo_fusion (visibility bookkeeping) and delaunay_mesher (Labatut graph-cut) can run on them.
Depth outside the official CasDiffMVS final mask is zeroed (= the same gate the user has been looking at)."""
import sys, struct, glob, os, numpy as np, cv2
from pathlib import Path
SRC = Path(sys.argv[1]); WS = Path(sys.argv[2]); WS.mkdir(parents=True, exist_ok=True)
for d in ["images", "sparse", "stereo/depth_maps", "stereo/normal_maps"]: (WS/d).mkdir(parents=True, exist_ok=True)
def read_pfm(p):
    with open(p, "rb") as f:
        assert f.readline().strip() == b"Pf"; w, h = map(int, f.readline().split()); s = float(f.readline())
        d = np.fromfile(f, "<f4" if s < 0 else ">f4").reshape(h, w); return np.flipud(d).astype(np.float32)
def read_cam(p):
    L = [l.rstrip() for l in open(p)]
    E = np.fromstring(" ".join(L[1:5]), sep=" ").reshape(4,4); K = np.fromstring(" ".join(L[7:10]), sep=" ").reshape(3,3)
    return E, K
def rot2quat(R):
    q = np.empty(4); t = np.trace(R)
    if t > 0: s = np.sqrt(t+1)*2; q[:] = [0.25*s, (R[2,1]-R[1,2])/s, (R[0,2]-R[2,0])/s, (R[1,0]-R[0,1])/s]
    elif R[0,0] > R[1,1] and R[0,0] > R[2,2]: s = np.sqrt(1+R[0,0]-R[1,1]-R[2,2])*2; q[:] = [(R[2,1]-R[1,2])/s, 0.25*s, (R[0,1]+R[1,0])/s, (R[0,2]+R[2,0])/s]
    elif R[1,1] > R[2,2]: s = np.sqrt(1+R[1,1]-R[0,0]-R[2,2])*2; q[:] = [(R[0,2]-R[2,0])/s, (R[0,1]+R[1,0])/s, 0.25*s, (R[1,2]+R[2,1])/s]
    else: s = np.sqrt(1+R[2,2]-R[0,0]-R[1,1])*2; q[:] = [(R[1,0]-R[0,1])/s, (R[0,2]+R[2,0])/s, (R[1,2]+R[2,1])/s, 0.25*s]
    return q / np.linalg.norm(q)
def write_mat(p, arr):  # COLMAP Mat<float>: "w&h&c&" then float32 [slice][row][col]
    if arr.ndim == 2: arr = arr[None]
    c, h, w = arr.shape
    with open(p, "wb") as f: f.write(f"{w}&{h}&{c}&".encode()); np.ascontiguousarray(arr.astype("<f4")).tofile(f)
cams = sorted(glob.glob(str(SRC/"cams/*_cam.txt"))); names = []
E0, K0 = read_cam(cams[0]); h, w = read_pfm(str(SRC/"depth_est/00000000.pfm")).shape
img_records = []; stats = []; cam_records = []
u, v = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
for i, cp in enumerate(cams):
    vid = os.path.basename(cp)[:8]; name = f"{vid}.jpg"; names.append(name)
    E, K = read_cam(cp); assert np.allclose(K, K0, rtol=0.1), (cp, K)
    R, t = E[:3,:3], E[:3,3]
    cam_records.append((i+1, K)); img_records.append((i+1, rot2quat(R), t, name))
    src_img = SRC/"images"/name
    im = cv2.imread(str(src_img)); assert im.shape[:2] == (h, w), (src_img, im.shape); cv2.imwrite(str(WS/"images"/name), im, [cv2.IMWRITE_JPEG_QUALITY, 95])
    depth = read_pfm(str(SRC/f"depth_est/{vid}.pfm"))
    mask = cv2.imread(str(SRC/f"mask/{vid}_final.png"), cv2.IMREAD_GRAYSCALE) > 0
    depth = np.where(mask & (depth > 0), depth, 0).astype(np.float32)
    # normals in camera frame from the (unmasked) depth, oriented towards the camera
    X = (u - K[0,2]) / K[0,0] * depth; Y = (v - K[1,2]) / K[1,1] * depth; P = np.stack([X, Y, depth], -1)
    dpu = np.gradient(P, axis=1); dpv = np.gradient(P, axis=0); n = np.cross(dpu, dpv)
    n /= (np.linalg.norm(n, axis=-1, keepdims=True) + 1e-12)
    flip = (np.sum(n * P, -1) > 0); n[flip] *= -1
    n[depth <= 0] = 0
    write_mat(WS/f"stereo/depth_maps/{name}.geometric.bin", depth)
    write_mat(WS/f"stereo/normal_maps/{name}.geometric.bin", np.transpose(n, (2,0,1)))
    stats.append(mask.mean())
with open(WS/"sparse/cameras.bin", "wb") as f:
    f.write(struct.pack("<Q", len(cam_records)))
    for cid, K in cam_records:
        f.write(struct.pack("<ii", cid, 1)); f.write(struct.pack("<QQ", w, h)); f.write(struct.pack("<4d", K[0,0], K[1,1], K[0,2], K[1,2]))
with open(WS/"sparse/images.bin", "wb") as f:
    f.write(struct.pack("<Q", len(img_records)))
    for iid, q, t, name in img_records:
        f.write(struct.pack("<i", iid)); f.write(struct.pack("<4d", *q)); f.write(struct.pack("<3d", *t)); f.write(struct.pack("<i", iid))
        f.write(name.encode() + b"\x00"); f.write(struct.pack("<Q", 0))
with open(WS/"sparse/points3D.bin", "wb") as f: f.write(struct.pack("<Q", 0))
(WS/"stereo/fusion.cfg").write_text("\n".join(names) + "\n")
print(f"workspace {WS}: {len(names)} images {w}x{h}, K fx {K0[0,0]:.2f} cx {K0[0,2]:.2f}; final-mask coverage mean {np.mean(stats):.3f}")
