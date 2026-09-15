#!/usr/bin/env python3.11
"""Math-free packer: copies the fixture builder's INPUT values (prep_phone_fixture.py lines 68-108) into flat binaries
for the C++ session-table gate. No arithmetic here except reading files.
  frames.f64  NF × 14: frame_id fx fy cx cy image_w image_h qw qx qy qz tx ty tz  (registered poses sorted by frame_id)
  points.f32  Npts × 3 from official_sfm_sparse.ply (x y z f4; r g b u1 skipped)
  names.txt   jpeg basenames in the same order"""
import json, os, sys, numpy as np
O, OUT = sys.argv[1], sys.argv[2]; os.makedirs(OUT, exist_ok=True)
meta = json.load(open(f"{O}/official_sfm_sparse_meta.json"))
fed = {json.loads(l)["frameId"]: json.loads(l) for l in open(f"{O}/official_sfm_fed_frames.jsonl") if l.strip()}
poses = [p for p in meta["poses"] if p.get("registered")]; poses.sort(key=lambda p: p["frame_id"])
rows = []; names = []
for p in poses:
    fid = p["frame_id"]; jpg = os.path.basename(fed[fid]["jpegPath"]); sc = json.load(open(f"{O}/sidecars/{jpg.replace('.jpg','.json')}"))
    fx, fy, cx, cy = sc["intrinsics_fxfycxcy"]; q = p["quat_wxyz"]; t = p["t"]
    rows.append([fid, fx, fy, cx, cy, sc["image_w"], sc["image_h"], q[0], q[1], q[2], q[3], t[0], t[1], t[2]]); names.append(jpg)
np.array(rows, np.float64).tofile(f"{OUT}/frames.f64"); open(f"{OUT}/names.txt", "w").write("\n".join(names) + "\n")
raw = open(f"{O}/official_sfm_sparse.ply", "rb").read(); he = raw.index(b"end_header\n") + 11
npt = int([l for l in raw[:he].decode("latin1").split("\n") if "element vertex" in l][0].split()[-1])
rec = np.frombuffer(raw[he:he+npt*15], dtype=[("x", "<f4"), ("y", "<f4"), ("z", "<f4"), ("r", "u1"), ("g", "u1"), ("b", "u1")])
np.stack([rec["x"], rec["y"], rec["z"]], 1).astype(np.float32).tofile(f"{OUT}/points.f32")
print(f"frames {len(rows)}  points {npt}  -> {OUT}")
