#!/usr/bin/env python3
"""Rebuild the new-cut cloud filtered to conf>=6 windows ONLY, so it is
apples-to-apples with yesterday's easy_postB (old-cut 11 conf>=6 windows).
Reuses expAC cached per-window depth + Fix B scales. No re-inference.
"""
import json
from pathlib import Path
import numpy as np
import cv2

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
RUN = Path("data/expAC_rewindow_span_2026_06_13")
WIN_DIR = RUN / "windows"
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
CONF_BAR = 6.0
CONF_PCT = 40.0

man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
frames = [r for r in man]  # spatial-order; expAC frame_idx indexes the dir-filtered list

# rebuild the same frames list expAC used (frames that have az/el)
bundle = json.loads((D / "capture_seq_k35_strict/photo_bundle.json").read_text())
azel = {fr["highresFilename"]: True for fr in bundle["frames"]}
frames = [r for r in man if r["jpegPath"].split("/")[-1] in azel]

rows = [json.loads(l) for l in (RUN / "expAC_results.jsonl").read_text().splitlines()]
wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
wrun = {r["win"]: r for r in rows if r["kind"] == "window_run"}
scales_row = [r for r in rows if r["kind"] == "scales"][0]
s_B = scales_row["s_B"]
confs = scales_row["conf_medians"]

good = [w for w in range(len(s_B)) if confs[w] >= CONF_BAR]
print(f"conf>=6 windows: {len(good)} -> {good}")
print(f"  confs: {[round(confs[w],1) for w in good]}")
print(f"  s_B:   {[round(s_B[w],3) for w in good]}")


def write_ply(name, use_scale):
    path = DELIVER / name
    fh = open(path, "wb")
    fh.write(("ply\nformat binary_little_endian 1.0\n"
              "element vertex 000000000000\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              "end_header\n").encode())
    count = 0
    for w in good:
        z = np.load(WIN_DIR / f"win_{w:02d}.npz")
        depth, conf = z["depth"].astype(np.float32), z["conf"].astype(np.float32)
        Ks, w2cs = z["K"].astype(np.float64), z["w2c"].astype(np.float64)
        s = s_B[w] if use_scale else 1.0
        n, H, W = depth.shape
        floor = np.percentile(conf, CONF_PCT)
        fidx = wdef[w]["frame_idx"]
        for k in range(n):
            zz = depth[k] * s
            m = (conf[k] >= floor) & (zz > 1e-3)
            vs, us = np.where(m)
            if not len(vs):
                continue
            img = cv2.imread(str(D / "capture_seq_k35_strict" / frames[fidx[k]]["jpegPath"]))
            img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
            cols = img[vs, us][:, ::-1]
            K = Ks[k]
            d = zz[vs, us].astype(np.float64)
            x = (us + 0.5 - K[0, 2]) / K[0, 0] * d
            y = (vs + 0.5 - K[1, 2]) / K[1, 1] * d
            cam = np.stack([x, y, d, np.ones_like(d)])
            pts = (np.linalg.inv(w2cs[k]) @ cam)[:3].T.astype(np.float32)
            rec = np.empty(len(pts), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
            rec["xyz"], rec["rgb"] = pts, cols
            fh.write(rec.tobytes())
            count += len(pts)
    fh.close()
    with open(path, "r+b") as f2:
        data = f2.read(200)
        f2.seek(data.find(b"000000000000"))
        f2.write(f"{count:012d}".encode())
    print(f"{name}: {count:,} pts")


write_ply("rewin_conf6_postB.ply", True)
write_ply("rewin_conf6_pre.ply", False)
print("DONE")
