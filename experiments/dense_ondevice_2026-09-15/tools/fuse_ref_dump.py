#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""参考发生器 = fuse_official.py 的逐帧循环原样(官方 filter.py check_geometric_consistency 原样调用),
只是把每帧的中间量落盘, 给 C++ 逐字节闸用:
  masks/{f:04d}.u8    final mask (H×W u8)      geosum/{f:04d}.i32  geo_mask_sum (H×W int32)
  davg/{f:04d}.f64    深度平均 (H×W float64)     xyz/{f:04d}.f32    该帧点 (N×3 float32, 官方顺序)
  col/{f:04d}.u8      颜色 (N×3 u8)
pack/ : 给 C++ 的原始输入 (depth.f32 NF×H×W, conf{k}.f32, rgb.u8 NF×H×W×3 已 resize 到 W×H, cams.f32, neighbors.i32,
        meta.txt, inv.f64 = 每帧 numpy.linalg.inv(K)(9)+inv(E)(16) 供隔离臂注入)
probe/ : 帧 0 前 PROBE_NSRC 个源视图的官方 reproject_with_depth 逐级中间量 (x_src,y_src,sampled,depth_reproj,x_reproj,y_reproj,mask)
用法: fuse_ref_dump.py --fixture FX --pred PRED --out OUT   (PYTHONPATH 决定用哪个 cv2: pip wheel=fp-contract on, 自编=off)
"""
import argparse, json, os, sys
import numpy as np
from PIL import Image
DIFFMVS = os.path.expanduser("~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
ap = argparse.ArgumentParser()
ap.add_argument("--fixture", required=True); ap.add_argument("--pred", required=True); ap.add_argument("--out", required=True)
ap.add_argument("--geo-mask-thres", type=int, default=3); ap.add_argument("--geo-pixel-thres", type=float, default=1.0)
ap.add_argument("--geo-depth-thres", type=float, default=0.01); ap.add_argument("--photo-thres", type=float, nargs=3, default=[0.3, 0.5, 0.5])
ap.add_argument("--probe-nsrc", type=int, default=3)
a = ap.parse_args()
sys.path.insert(0, DIFFMVS)
import cv2
from filter import check_geometric_consistency, reproject_with_depth
print("cv2", cv2.__version__, cv2.__file__, "numpy", np.__version__, flush=True)
FX = a.fixture; meta = json.load(open(f"{FX}/frames.json")); NF, W, H = meta["count"], meta["width"], meta["height"]
CM = np.fromfile(f"{FX}/cams.f32", np.float32).reshape(NF, 36); NB = np.fromfile(f"{FX}/neighbors.i32", np.int32).reshape(NF, meta["num_src"])
D = [np.load(f"{a.pred}/depth/{f:04d}.npy").astype(np.float32) for f in range(NF)]
CF = [[np.load(f"{a.pred}/conf{k}/{f:04d}.npy").astype(np.float32) for f in range(NF)] for k in range(3)]
for k in range(3):
    assert CF[k][0].shape == D[0].shape, "conf 分辨率与深度不同, 本 dump 不处理 resize"
for sub in ("masks", "geosum", "davg", "xyz", "col", "pack", "probe"): os.makedirs(f"{a.out}/{sub}", exist_ok=True)
RGB = np.stack([np.asarray(Image.open(f"{FX}/rgb/{f:08d}.jpg").resize((W, H))) for f in range(NF)]).astype(np.uint8)
np.stack(D).astype(np.float32).tofile(f"{a.out}/pack/depth.f32")
for k in range(3): np.stack(CF[k]).astype(np.float32).tofile(f"{a.out}/pack/conf{k}.f32")
RGB.tofile(f"{a.out}/pack/rgb.u8"); CM.tofile(f"{a.out}/pack/cams.f32"); NB.tofile(f"{a.out}/pack/neighbors.i32")
json.dump({"NF": NF, "W": W, "H": H, "num_src": int(meta["num_src"]), "geo_mask_thres": a.geo_mask_thres, "geo_pixel_thres": a.geo_pixel_thres,
           "geo_depth_thres": a.geo_depth_thres, "photo_thres": a.photo_thres, "cv2": cv2.__version__, "cv2_file": cv2.__file__}, open(f"{a.out}/pack/meta.json", "w"))
with open(f"{a.out}/pack/meta.txt", "w") as fh:
    fh.write(f"{NF} {W} {H} {int(meta['num_src'])} {a.geo_mask_thres} {a.geo_pixel_thres!r} {a.geo_depth_thres!r} {a.photo_thres[0]!r} {a.photo_thres[1]!r} {a.photo_thres[2]!r}\n")

def cam(f):
    E = np.eye(4, dtype=np.float64); E[:3, :3] = CM[f, 9:18].reshape(3, 3); E[:3, 3] = CM[f, 18:21]
    return CM[f, 0:9].reshape(3, 3).astype(np.float64), E
INV = np.zeros((NF, 25), np.float64)
for f in range(NF):
    Kf, Ef = cam(f); INV[f, :9] = np.linalg.inv(Kf).reshape(-1); INV[f, 9:] = np.linalg.inv(Ef).reshape(-1)
INV.tofile(f"{a.out}/pack/inv.f64")

# probe: frame 0, first probe-nsrc sources, official reproject_with_depth stage outputs
Kr0, Er0 = cam(0)
for j, s in enumerate(NB[0][:a.probe_nsrc]):
    Ks, Es = cam(int(s))
    depth_reproj, x_reproj, y_reproj, x_src, y_src = reproject_with_depth(D[0], Kr0, Er0, D[int(s)], Ks, Es)
    sampled = cv2.remap(D[int(s)], x_src, y_src, interpolation=cv2.INTER_LINEAR)   # identical call to filter.py:41
    gm, _, _, _ = check_geometric_consistency(D[0], Kr0, Er0, D[int(s)], Ks, Es, float(CM[0, 25]), float(CM[0, 24]), a.geo_pixel_thres, a.geo_depth_thres)
    for name, arr in (("x_src", x_src), ("y_src", y_src), ("sampled", sampled), ("depth_reproj", depth_reproj), ("x_reproj", x_reproj), ("y_reproj", y_reproj)):
        arr.astype(np.float32).tofile(f"{a.out}/probe/s{j}_{name}.f32")
    gm.astype(np.uint8).tofile(f"{a.out}/probe/s{j}_mask.u8")

tot = 0; ph_m = ge_m = fi_m = 0.0
for f in range(NF):
    Kr, Er = cam(f); ref_d = D[f]
    photo = np.ones_like(ref_d, bool)
    for k in range(3): photo &= (CF[k][f] > a.photo_thres[k])
    geo_sum = np.zeros_like(ref_d, np.int32); acc = np.zeros_like(ref_d, np.float64)
    for s in NB[f]:
        Ks, Es = cam(int(s))
        gm, d_rep, _, _ = check_geometric_consistency(ref_d, Kr, Er, D[int(s)], Ks, Es, float(CM[f, 25]), float(CM[f, 24]), a.geo_pixel_thres, a.geo_depth_thres)
        geo_sum += gm.astype(np.int32); acc += d_rep
    d_avg = (acc + ref_d) / (geo_sum + 1)
    geo = geo_sum >= a.geo_mask_thres; final = photo & geo
    ph_m += photo.mean(); ge_m += geo.mean(); fi_m += final.mean()
    final.astype(np.uint8).tofile(f"{a.out}/masks/{f:04d}.u8"); geo_sum.tofile(f"{a.out}/geosum/{f:04d}.i32"); d_avg.tofile(f"{a.out}/davg/{f:04d}.f64")
    yy, xx = np.mgrid[0:H, 0:W]; x, y, d = xx[final], yy[final], d_avg[final]
    xyz = np.linalg.inv(Kr) @ (np.vstack([x, y, np.ones_like(x)]) * d)
    Rr, tr = Er[:3, :3], Er[:3, 3]; P = ((xyz.T - tr) @ Rr).astype(np.float32)
    P.tofile(f"{a.out}/xyz/{f:04d}.f32"); RGB[f][final].astype(np.uint8).tofile(f"{a.out}/col/{f:04d}.u8"); tot += len(P)
    if f % 25 == 0: print(f"  帧{f:3d}/{NF} final {final.mean():.3f}", flush=True)
print(f"存活 photo {100*ph_m/NF:.2f}% geo {100*ge_m/NF:.2f}% final {100*fi_m/NF:.2f}%   点数 {tot:,}")
json.dump({"points": tot, "cv2": cv2.__version__, "cv2_file": cv2.__file__}, open(f"{a.out}/summary.json", "w"))
