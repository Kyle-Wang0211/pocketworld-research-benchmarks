"""Coverage-replay prototype (step 1 of PocketWorld capture-UX).

Goal: reproduce RealityScan's red/yellow/green capture-coverage feedback, with the
hard guarantees the user asked for:
  - NO drift   : points live in a FIXED world voxel grid (replay poses are fixed).
  - NO backtrack: a voxel's coverage state only ever INCREASES
                  (s_appear <= s_yellow <= s_green; color never regresses).
  - GROWS      : as more frames are "captured", new voxels appear (area up) and
                 existing voxels gain cameras/angles (red -> yellow -> green).

Signal = RealityScan's literal "camera coverage of each point": how many distinct
cameras observed a voxel, and from how diverse view angles.

Method (reuses pw_diffmvs's VERIFIED backprojection, 0.6px self-checked):
  per-frame DiffMVS depth (p1cache) -> world points (run.py eq.) -> world voxels;
  walk frames in capture order, accumulate per-voxel {camera count, azimuth bins}.

Output (to ~/Desktop/pocketworld_coverage/): voxels.bin + meta.json + cams.bin,
consumed by index.html (Three.js scrub/play viewer).

Usage: python3 coverage_replay.py [VOXEL_M] [STRIDE] [CONF] [GREEN_CNT] [GREEN_BINS]
"""
from __future__ import annotations
import sys, json, struct
from pathlib import Path
import numpy as np
import cv2

# ---- params ----
VOXEL      = float(sys.argv[1]) if len(sys.argv) > 1 else 0.03   # 3cm world voxels
STRIDE     = int(sys.argv[2])   if len(sys.argv) > 2 else 2      # pixel subsample
CONF_THR   = float(sys.argv[3]) if len(sys.argv) > 3 else 0.30   # DiffMVS conf gate
GREEN_CNT  = int(sys.argv[4])   if len(sys.argv) > 4 else 4      # cameras for green
GREEN_BINS = int(sys.argv[5])   if len(sys.argv) > 5 else 3      # distinct az bins for green
YELLOW_CNT = 2                                                   # cameras for yellow
N_AZ       = 8                                                   # azimuth bins (around +Y up)

ROOT  = Path(__file__).resolve().parents[2]
CAP   = ROOT / "data/official_da3_base_k35_strict_seq_2026_06_02/capture_seq_k35_strict"
OBASE = ROOT / "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/external_pose_k_vs_res_2026_06_10"
EXPAC = ROOT / "data/expAC_rewindow_span_2026_06_13"
P1    = ROOT / "tools/python/diffmvs_out/p1cache_diffmvs.npz"
PROC_H, PROC_W, NPZ_H = 512, 896, 504
OUTDIR = Path.home() / "Desktop" / "pocketworld_coverage"
OUTDIR.mkdir(parents=True, exist_ok=True)


def scaled_K(K):
    K = K.astype(np.float32).copy(); K[1, :] *= PROC_H / NPZ_H; return K

def cam_center(w2c):
    return -w2c[:3, :3].T @ w2c[:3, 3]


def build_frame_table():
    """mi -> (K@512x896, w2c, center). Mirrors pw_diffmvs_geomcons.build_frame_table."""
    man = json.load(open(OBASE / "k414_spatial_order_manifest.json"))
    frames_man = man["frames"]; spatial = man["spatialOrder"]
    rows = [json.loads(l) for l in open(EXPAC / "expAC_results.jsonl")]
    wdef = {r["win"]: r for r in rows if r["kind"] == "window_def"}
    Kmap, wmap = {}, {}
    for win, wd in wdef.items():
        z = np.load(EXPAC / "windows" / f"win_{win:02d}.npz")
        for j, mi in enumerate(wd["frame_idx"]):
            if mi not in Kmap:
                Kmap[mi] = scaled_K(z["K"][j]); wmap[mi] = z["w2c"][j].astype(np.float32)
    centers = {mi: cam_center(wmap[mi]) for mi in Kmap}
    return frames_man, spatial, Kmap, wmap, centers


def load_rgb(jpeg_rel):
    bgr = cv2.imread(str(CAP / jpeg_rel))
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return cv2.resize(rgb, (PROC_W, PROC_H), interpolation=cv2.INTER_AREA)


def backproject(depth, K, w2c):
    H, W = depth.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    x = (uu - K[0, 2]) / K[0, 0] * depth
    y = (vv - K[1, 2]) / K[1, 1] * depth
    cam = np.stack([x, y, depth], -1).reshape(-1, 3)
    R, t = w2c[:3, :3], w2c[:3, 3]
    return (R.T @ (cam.T - t[:, None])).T          # (HW,3) world


def main():
    frames_man, spatial, Kmap, wmap, centers = build_frame_table()
    z = np.load(P1, allow_pickle=True)
    depth_all, conf_all = z["depth"], z["conf"]
    drange_all = z["drange"]; cache_frames = z["frames"].tolist()
    f2cache = {mi: i for i, mi in enumerate(cache_frames)}
    print(f"frame_table={len(Kmap)}  p1cache_frames={len(cache_frames)}", flush=True)

    # capture order = spatialOrder restricted to frames we have depth + pose for
    order = [mi for mi in spatial if mi in f2cache and mi in Kmap]
    print(f"replay steps={len(order)} (spatial-order keyframes)", flush=True)

    # per-voxel accumulator: key(int64) -> [cnt, az_mask, s_appear, s_yellow, s_green, rsum, gsum, bsum, npx]
    vox = {}
    OFF = np.int64(32768); B = np.int64(65536); B2 = B * B          # voxel-key packing (handles negatives)
    def pack(idx):                                                  # idx (N,3) int64 -> key (N,) int64
        return (idx[:, 0] + OFF) + (idx[:, 1] + OFF) * B + (idx[:, 2] + OFF) * B2
    def unpack(keys):                                               # keys (N,) -> (N,3) int64
        kz = keys // B2; r = keys - kz * B2; ky = r // B; kx = r - ky * B
        return np.stack([kx - OFF, ky - OFF, kz - OFF], 1)

    for step, mi in enumerate(order):
        ci = f2cache[mi]
        depth = depth_all[ci].astype(np.float32)
        conf  = conf_all[ci].astype(np.float32)
        dmin, dmax = float(drange_all[ci][0]), float(drange_all[ci][1])
        K, w2c = Kmap[mi], wmap[mi]
        rgb = load_rgb(frames_man[mi]["jpegPath"]).reshape(-1, 3).astype(np.float32) / 255.0

        world = backproject(depth, K, w2c)
        d = depth.reshape(-1); c = conf.reshape(-1)
        good = (d > 0) & np.isfinite(world).all(1) & (c >= CONF_THR) & (d < 0.97 * dmax)
        # pixel subsample for speed/density
        if STRIDE > 1:
            mask2d = np.zeros((PROC_H, PROC_W), bool); mask2d[::STRIDE, ::STRIDE] = True
            good &= mask2d.reshape(-1)
        W = world[good]; COL = rgb[good]
        if len(W) == 0:
            continue

        # azimuth bin (around +Y up) of view direction voxel->camera
        cc = centers[mi]
        vd = cc[None, :] - W
        az = (np.arctan2(vd[:, 2], vd[:, 0]) + np.pi) / (2 * np.pi)     # 0..1
        azbin = np.minimum((az * N_AZ).astype(np.int64), N_AZ - 1)
        azbit = (1 << azbin).astype(np.int64)

        vk = pack(np.floor(W / VOXEL).astype(np.int64))                # packed voxel key
        # collapse within frame: per unique voxel -> OR of az bits + mean color
        uk, inv = np.unique(vk, return_inverse=True)
        ub = np.zeros(len(uk), np.int64)
        np.bitwise_or.at(ub, inv, azbit)
        rs = np.zeros(len(uk)); gs = np.zeros(len(uk)); bs = np.zeros(len(uk)); nn = np.zeros(len(uk))
        np.add.at(rs, inv, COL[:, 0]); np.add.at(gs, inv, COL[:, 1]); np.add.at(bs, inv, COL[:, 2])
        np.add.at(nn, inv, 1.0)

        for k, b, r_, g_, b_, n_ in zip(uk.tolist(), ub.tolist(), rs, gs, bs, nn):
            rec = vox.get(k)
            if rec is None:
                vox[k] = [1, b, step, -1, -1, r_, g_, b_, n_]
            else:
                rec[0] += 1; rec[1] |= b; rec[5] += r_; rec[6] += g_; rec[7] += b_; rec[8] += n_
                if rec[3] < 0 and rec[0] >= YELLOW_CNT:
                    rec[3] = step
                if rec[4] < 0 and rec[0] >= GREEN_CNT and bin(rec[1]).count("1") >= GREEN_BINS:
                    rec[4] = step
        if step % 40 == 0:
            print(f"  step {step}/{len(order)} voxels={len(vox):,}", flush=True)

    # ---- export (vectorized) ----
    N = len(vox); NS = len(order)
    keys = np.fromiter(vox.keys(), np.int64, N)
    recs = np.array(list(vox.values()), np.float64)                # (N,9)
    idx = unpack(keys)                                             # (N,3) int64
    centerxyz = (idx + 0.5) * VOXEL
    npx = np.maximum(recs[:, 8], 1.0)
    buf = np.zeros((N, 9), np.float32)
    buf[:, 0:3] = centerxyz
    buf[:, 3] = recs[:, 5] / npx; buf[:, 4] = recs[:, 6] / npx; buf[:, 5] = recs[:, 7] / npx
    buf[:, 6] = recs[:, 2]; buf[:, 7] = recs[:, 3]; buf[:, 8] = recs[:, 4]   # s_appear, s_yellow, s_green
    buf.tofile(OUTDIR / "voxels.bin")

    cams = np.array([centers[mi] for mi in order], np.float32)
    cams.tofile(OUTDIR / "cams.bin")

    ctr = buf[:, :3].mean(0).tolist()
    mn = buf[:, :3].min(0).tolist(); mx = buf[:, :3].max(0).tolist()
    meta = dict(n_voxels=N, n_steps=NS, voxel=VOXEL, center=ctr, bbox=[mn, mx],
                green_cnt=GREEN_CNT, green_bins=GREEN_BINS, yellow_cnt=YELLOW_CNT,
                conf_thr=CONF_THR, stride=STRIDE)
    json.dump(meta, open(OUTDIR / "meta.json", "w"), indent=2)
    print(f"\nDONE  voxels={N:,}  steps={NS}  -> {OUTDIR}", flush=True)
    # green/yellow/red final tally
    sg = buf[:, 8] >= 0; sy = (buf[:, 7] >= 0) & ~sg
    print(f"final: green={sg.sum():,}  yellow={sy.sum():,}  red={N - sg.sum() - sy.sum():,}", flush=True)


if __name__ == "__main__":
    main()
