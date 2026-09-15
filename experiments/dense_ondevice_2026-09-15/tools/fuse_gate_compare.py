#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""逐字节闸: fuse_gate_compare.py REF_DIR CPP_DIR [--probe-ref DIR --probe-cpp DIR]
比较 masks/geosum/davg/xyz/col 每帧文件 (浮点按位比较, NaN 安全), 以及探针逐级中间量。
退出码 0 = 全部逐位相同。"""
import argparse, glob, os, sys
import numpy as np
ap = argparse.ArgumentParser()
ap.add_argument("ref"); ap.add_argument("cpp")
ap.add_argument("--probe-ref"); ap.add_argument("--probe-cpp"); ap.add_argument("--probe-nsrc", type=int, default=3)
a = ap.parse_args()
UINT = {np.float32: np.uint32, np.float64: np.uint64}

def bits_ne(r, c, dtype):
    if dtype in UINT:
        return r.view(UINT[dtype]) != c.view(UINT[dtype])
    return r != c

def cmp_dir(sub, dtype, per_frame=False):
    files = sorted(glob.glob(f"{a.ref}/{sub}/*"))
    tot = diff = 0; bad_frames = []; maxabs = 0.0; first = None
    for fr in files:
        fc = f"{a.cpp}/{sub}/{os.path.basename(fr)}"
        if not os.path.exists(fc):
            print(f"  {sub}: 缺 {fc}"); bad_frames.append(os.path.basename(fr)); continue
        r = np.fromfile(fr, dtype); c = np.fromfile(fc, dtype)
        if r.size != c.size:
            print(f"  {sub} {os.path.basename(fr)}: 长度 {r.size} vs {c.size}"); bad_frames.append(os.path.basename(fr)); tot += max(r.size, c.size); diff += max(r.size, c.size); continue
        d = bits_ne(r, c, dtype); nd = int(d.sum()); tot += r.size; diff += nd
        if nd:
            bad_frames.append(os.path.basename(fr))
            if first is None: first = (os.path.basename(fr), nd, r[d][:4], c[d][:4])
            if dtype in UINT: maxabs = max(maxabs, float(np.nanmax(np.abs(r[d].astype(np.float64) - c[d].astype(np.float64)))))
            if per_frame: print(f"    {sub} {os.path.basename(fr)}: {nd} 个不同")
    ok = diff == 0 and not bad_frames
    print(f"{'✅' if ok else '🔴'} {sub:7s} 文件 {len(files):3d}  元素 {tot:>12,}  不同 {diff:>10,}  ({100.0*diff/max(tot,1):.6f}%)  坏帧 {len(bad_frames)}" + (f"  max|Δ| {maxabs:.3g}" if dtype in UINT and diff else ""))
    if first: print(f"    首个不同: {first[0]} n={first[1]} ref={first[2]} cpp={first[3]}")
    return ok

allok = True
for sub, dt in (("masks", np.uint8), ("geosum", np.int32), ("davg", np.float64), ("xyz", np.float32), ("col", np.uint8)):
    allok &= cmp_dir(sub, dt)
try:
    import json
    pr = json.load(open(f"{a.ref}/summary.json")); print(f"参考点数 {pr['points']:,}  cv2={pr.get('cv2')} {pr.get('cv2_file','')}")
except Exception as e:
    print("summary.json:", e)

if a.probe_ref and a.probe_cpp:
    print("— 探针 (帧0 逐级中间量) —")
    for j in range(a.probe_nsrc):
        for name, dt in (("x_src", np.float32), ("y_src", np.float32), ("sampled", np.float32), ("depth_reproj", np.float32), ("x_reproj", np.float32), ("y_reproj", np.float32), ("mask", np.uint8)):
            fr = f"{a.probe_ref}/s{j}_{name}.{'u8' if dt is np.uint8 else 'f32'}"; fc = f"{a.probe_cpp}/s{j}_{name}.{'u8' if dt is np.uint8 else 'f32'}"
            if not (os.path.exists(fr) and os.path.exists(fc)): print(f"  s{j} {name}: 缺文件"); allok = False; continue
            r = np.fromfile(fr, dt); c = np.fromfile(fc, dt); d = bits_ne(r, c, dt); nd = int(d.sum())
            extra = ""
            if nd and dt is np.float32:
                extra = f"  max|Δ| {float(np.nanmax(np.abs(r[d].astype(np.float64)-c[d].astype(np.float64)))):.3g}  例 ref={r[d][:3]} cpp={c[d][:3]}"
            print(f"  {'✅' if nd == 0 else '🔴'} s{j} {name:13s} 不同 {nd:>8,} / {r.size:,} ({100.0*nd/r.size:.5f}%){extra}")
            allok &= (nd == 0)
print("GATE", "PASS" if allok else "FAIL")
sys.exit(0 if allok else 1)
