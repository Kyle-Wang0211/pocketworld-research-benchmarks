#!/usr/bin/env python3
"""expAF: UNION cut — fuse ALL conf>=6 windows from BOTH the old
spatial-stride cut AND the new FPS peak-band cut, each Fix-B-scaled to
the SAME 29k sparse anchors. Because Fix B anchors every window
independently to one metric frame, windows from any strategy / any
span can be freely unioned. This is "各取所长": old cut keeps the
left/cabinet (incl. its 51-60° wide windows), new cut adds the right
background, redundancy is harmless (offline full-delivery).

Dedup is by FRAME-SET Jaccard only (>=0.9 = genuinely the same 18
frames -> keep higher conf). No center-distance / span thresholds.
No re-inference — old depth from expQ, new depth from expAC npz.
"""
import json
from pathlib import Path
import numpy as np
import cv2
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import da3_window_scale_fixb as fixb

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
Q = O / "expQ_spatial_windows"
EXPAC = Path("data/expAC_rewindow_span_2026_06_13")
ANCH = Path("data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz")
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
CONF_BAR = 6.0
CONF_PCT = 40.0
JACCARD_DUP = 0.9

man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
bundle = json.loads((D / "capture_seq_k35_strict/photo_bundle.json").read_text())
azel = {fr["highresFilename"]: True for fr in bundle["frames"]}
frames = [r for r in man if r["jpegPath"].split("/")[-1] in azel]
assert len(frames) == len(man), f"frame/dir mismatch {len(frames)} vs {len(man)}"
print(f"frames: {len(frames)}")

z = np.load(ANCH)
anchors = fixb.AnchorSet(z["pts"], z["obs_frame"], z["obs_uv"], z["obs_aidx"])

cands = []  # each: dict(src, win, fidx(global), conf, depth_path-or-arr, ...)


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1))
        out[:, :3, :] = ext
        return out
    return ext.reshape(-1, 4, 4)


# ---- OLD spatial cut (expQ window_000..044) ----
for w in range(45):
    d = Q / f"window_{w:03d}"
    if not (d / "pytorch_conf.npy").exists():
        continue
    conf = np.load(d / "pytorch_conf.npy").astype(np.float32)
    cm = float(np.median(conf))
    if cm < CONF_BAR:
        continue
    fidx = list(range(w * 9, w * 9 + 18))
    cands.append({"src": "old", "win": w, "fidx": fidx, "conf": cm, "dir": d})

# ---- NEW FPS cut (expAC) ----
rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
scales = [r for r in rows if r["kind"] == "scales"][0]
for w in range(len(scales["s_B"])):
    if scales["conf_medians"][w] < CONF_BAR:
        continue
    cands.append({"src": "new", "win": w, "fidx": list(wdef[w]["frame_idx"]),
                  "conf": scales["conf_medians"][w],
                  "npz": EXPAC / "windows" / f"win_{w:02d}.npz"})

print(f"conf>=6 candidates: {sum(1 for c in cands if c['src']=='old')} old + "
      f"{sum(1 for c in cands if c['src']=='new')} new = {len(cands)}")

# ---- dedup by frame-set Jaccard ----
cands.sort(key=lambda c: -c["conf"])
kept, removed = [], []
for c in cands:
    s = set(c["fidx"])
    dup = False
    for k in kept:
        inter = len(s & set(k["fidx"]))
        union = len(s | set(k["fidx"]))
        if inter / union >= JACCARD_DUP:
            removed.append((c["src"], c["win"], k["src"], k["win"], inter / union))
            dup = True
            break
    if not dup:
        kept.append(c)
print(f"dedup (Jaccard>={JACCARD_DUP}): removed {len(removed)} -> {len(kept)} windows kept")
for r in removed:
    print(f"  drop {r[0]}win{r[1]} (dup of {r[2]}win{r[3]}, J={r[4]:.2f})")


def load_depth(c):
    if c["src"] == "old":
        d = c["dir"]
        return (np.load(d / "pytorch_depth.npy").astype(np.float32),
                np.load(d / "pytorch_conf.npy").astype(np.float32),
                np.load(d / "pytorch_intrinsics.npy").astype(np.float64),
                w2c4(np.load(d / "pytorch_extrinsics.npy")))
    z = np.load(c["npz"])
    return (z["depth"].astype(np.float32), z["conf"].astype(np.float32),
            z["K"].astype(np.float64), w2c4(z["w2c"]))


# ---- Fix B scale per kept window ----
for c in kept:
    depth, conf, K, w2c = load_depth(c)
    s, nobs = fixb.fit_window_scale(anchors, depth, conf, w2c, c["fidx"])
    c["scale"] = s if s is not None else 1.0
    c["fitted"] = s is not None
    print(f"  {c['src']}win{c['win']:02d} conf {c['conf']:.1f}  s_B "
          f"{c['scale']:.3f}{'' if c['fitted'] else ' (FALLBACK 1.0)'}  obs {nobs}")

# ---- backproject union ----
path = DELIVER / "union_postB.ply"
fh = open(path, "wb")
fh.write(("ply\nformat binary_little_endian 1.0\n"
          "element vertex 000000000000\n"
          "property float x\nproperty float y\nproperty float z\n"
          "property uchar red\nproperty uchar green\nproperty uchar blue\n"
          "end_header\n").encode())
count = 0
for c in kept:
    depth, conf, K, w2c = load_depth(c)
    s = c["scale"]
    n, H, W = depth.shape
    floor = np.percentile(conf, CONF_PCT)
    for k in range(n):
        zz = depth[k] * s
        m = (conf[k] >= floor) & (zz > 1e-3)
        vs, us = np.where(m)
        if not len(vs):
            continue
        img = cv2.imread(str(D / "capture_seq_k35_strict" / man[c["fidx"][k]]["jpegPath"]))
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
        cols = img[vs, us][:, ::-1]
        Ki = K[k]
        dd = zz[vs, us].astype(np.float64)
        x = (us + 0.5 - Ki[0, 2]) / Ki[0, 0] * dd
        y = (vs + 0.5 - Ki[1, 2]) / Ki[1, 1] * dd
        cam = np.stack([x, y, dd, np.ones_like(dd)])
        pts = (np.linalg.inv(w2c[k]) @ cam)[:3].T.astype(np.float32)
        rec = np.empty(len(pts), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
        rec["xyz"], rec["rgb"] = pts, cols
        fh.write(rec.tobytes())
        count += len(pts)
fh.close()
with open(path, "r+b") as f2:
    data = f2.read(200)
    f2.seek(data.find(b"000000000000"))
    f2.write(f"{count:012d}".encode())
print(f"union_postB.ply: {count:,} pts from {len(kept)} windows "
      f"(spans {min(0,0) if False else ''}) -> {path}")
