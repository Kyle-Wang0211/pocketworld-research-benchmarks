#!/usr/bin/env python3
"""expAG: normal-colored point clouds for the OLD-11 and NEW-12 conf>=6
Fix-B window sets, SEPARATELY (user: 不要建在并集云上, 分别建).

Normals = depth-space cross-product (the ship-plan method, no PCA / no
learned), oriented toward camera, world-rotated. Point color = world
normal mapped to RGB ((n*0.5+0.5)*255). Read: coherent surface ->
smooth color patch; noisy/flipped normals -> rainbow speckle.

No re-inference. Old depth from expQ, new depth from expAC npz, Fix B
scales from each run's results. Stride for browser viewability; full
normals are computed, only the OUTPUT is strided.
"""
import json
from pathlib import Path
import numpy as np

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
Q = O / "expQ_spatial_windows"
EXPAC = Path("data/expAC_rewindow_span_2026_06_13")
ANCH = Path("data/expF2_easy_clouds_2026_06_12/anchors_obs_414.npz")
DELIVER = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
CONF_BAR = 6.0
CONF_PCT = 40.0
STRIDE = 3
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import da3_window_scale_fixb as fixb

man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
bundle = json.loads((D / "capture_seq_k35_strict/photo_bundle.json").read_text())
azel = {fr["highresFilename"]: True for fr in bundle["frames"]}
frames = [r for r in man if r["jpegPath"].split("/")[-1] in azel]
z = np.load(ANCH)
anchors = fixb.AnchorSet(z["pts"], z["obs_frame"], z["obs_uv"], z["obs_aidx"])


def w2c4(ext):
    ext = np.asarray(ext, np.float64)
    if ext.shape[-2:] == (3, 4):
        out = np.tile(np.eye(4), (len(ext), 1, 1))
        out[:, :3, :] = ext
        return out
    return ext.reshape(-1, 4, 4)


def depth_normals(depth, K):
    """Camera-space normal per pixel via cross-product of neighbor 3D diffs."""
    H, W = depth.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu + 0.5 - K[0, 2]) / K[0, 0] * depth
    y = (vv + 0.5 - K[1, 2]) / K[1, 1] * depth
    P = np.stack([x, y, depth], axis=-1)            # H,W,3 camera-space
    dPdu = np.zeros_like(P); dPdv = np.zeros_like(P)
    dPdu[:, 1:-1, :] = P[:, 2:, :] - P[:, :-2, :]
    dPdv[1:-1, :, :] = P[2:, :, :] - P[:-2, :, :]
    n = np.cross(dPdu, dPdv)
    ln = np.linalg.norm(n, axis=-1, keepdims=True)
    n = np.divide(n, ln, out=np.zeros_like(n), where=ln > 1e-9)
    # orient toward camera: point P is in front (+z), camera at origin;
    # viewing dir to point = P; normal should oppose it (n·P < 0)
    flip = (np.sum(n * P, axis=-1) > 0)
    n[flip] = -n[flip]
    return n, P


def build(tag, windows):
    path = DELIVER / f"normals_{tag}.ply"
    fh = open(path, "wb")
    fh.write(("ply\nformat binary_little_endian 1.0\n"
              "element vertex 000000000000\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\n"
              "end_header\n").encode())
    count = 0
    for w in windows:
        depth, conf, K, w2c, fidx = w["depth"], w["conf"], w["K"], w["w2c"], w["fidx"]
        s = w["scale"]
        n, _, _ = depth.shape
        floor = np.percentile(conf, CONF_PCT)
        for k in range(n):
            dk = depth[k] * s
            nrm, _ = depth_normals(dk, K[k])           # H,W,3 cam-space normal
            m = (conf[k] >= floor) & (dk > 1e-3)
            vs, us = np.where(m)
            sel = (vs % STRIDE == 0) & (us % STRIDE == 0)
            vs, us = vs[sel], us[sel]
            if not len(vs):
                continue
            Ki = K[k]
            dd = dk[vs, us].astype(np.float64)
            x = (us + 0.5 - Ki[0, 2]) / Ki[0, 0] * dd
            y = (vs + 0.5 - Ki[1, 2]) / Ki[1, 1] * dd
            cam = np.stack([x, y, dd, np.ones_like(dd)])
            c2w = np.linalg.inv(w2c[k])
            pts = (c2w @ cam)[:3].T.astype(np.float32)
            # world-rotate the normals
            ncam = nrm[vs, us]                          # M,3
            nworld = (c2w[:3, :3] @ ncam.T).T
            ln = np.linalg.norm(nworld, axis=1, keepdims=True)
            nworld = np.divide(nworld, ln, out=np.zeros_like(nworld), where=ln > 1e-9)
            cols = np.clip((nworld * 0.5 + 0.5) * 255, 0, 255).astype(np.uint8)
            rec = np.empty(len(pts), dtype=[("xyz", np.float32, 3), ("rgb", np.uint8, 3)])
            rec["xyz"], rec["rgb"] = pts, cols
            fh.write(rec.tobytes())
            count += len(pts)
    fh.close()
    with open(path, "r+b") as f2:
        data = f2.read(200)
        f2.seek(data.find(b"000000000000"))
        f2.write(f"{count:012d}".encode())
    print(f"normals_{tag}.ply: {count:,} pts ({len(windows)} windows)")


# ---- OLD 11 conf>=6 windows ----
old_w = []
for w in range(45):
    d = Q / f"window_{w:03d}"
    if not (d / "pytorch_conf.npy").exists():
        continue
    conf = np.load(d / "pytorch_conf.npy").astype(np.float32)
    if float(np.median(conf)) < CONF_BAR:
        continue
    depth = np.load(d / "pytorch_depth.npy").astype(np.float32)
    K = np.load(d / "pytorch_intrinsics.npy").astype(np.float64)
    w2c = w2c4(np.load(d / "pytorch_extrinsics.npy"))
    fidx = list(range(w * 9, w * 9 + 18))
    s, _ = fixb.fit_window_scale(anchors, depth, conf, w2c, fidx)
    old_w.append({"depth": depth, "conf": conf, "K": K, "w2c": w2c,
                  "fidx": fidx, "scale": s if s else 1.0})
print(f"OLD conf>=6: {len(old_w)} windows")

# ---- NEW 12 conf>=6 windows ----
rows = [json.loads(l) for l in (EXPAC / "expAC_results.jsonl").read_text().splitlines()]
wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
scales = [r for r in rows if r["kind"] == "scales"][0]
new_w = []
for w in range(len(scales["s_B"])):
    if scales["conf_medians"][w] < CONF_BAR:
        continue
    zz = np.load(EXPAC / "windows" / f"win_{w:02d}.npz")
    new_w.append({"depth": zz["depth"].astype(np.float32),
                  "conf": zz["conf"].astype(np.float32),
                  "K": zz["K"].astype(np.float64), "w2c": w2c4(zz["w2c"]),
                  "fidx": list(wdef[w]["frame_idx"]),
                  "scale": scales["s_B"][w]})
print(f"NEW conf>=6: {len(new_w)} windows")

build("old11", old_w)
build("new12", new_w)
print("DONE")
