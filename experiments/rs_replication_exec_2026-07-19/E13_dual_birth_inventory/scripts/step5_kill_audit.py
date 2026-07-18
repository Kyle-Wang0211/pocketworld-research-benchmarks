#!/usr/bin/env python3.11
"""E13 step5 — miskill audit: project killed losers onto real photos.

For each audited kill: crop the loser's first observation from the original
3840x2160 photo (same resolution SfM consumed). Red circle = loser's observed
pixel; green cross = winner's projection into the same frame; cyan cross =
loser's own projection. Panels: (a) ALL true-floor suspects (winner >15mm away)
(b) 36 random kills (fixed seed). JSON with per-sample numbers accompanies.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, "/Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714/experiments/rs_replication_exec_2026-07-19/E13_dual_birth_inventory/scripts")
from e13_lib import D, E13, OFF_RUN, PHOTOS, qvec2rot, read_cameras_bin, read_images_bin_full

TILE = 300
COLS = 6


def load_frame_map(cap):
    import json as j
    m = {}
    with open(f"{D}/data/pocketworld_captures/{cap}/device_full_pull_2026-07-17/sfm_fed_frames.jsonl") as f:
        for line in f:
            r = j.loads(line)
            m[r["frameId"] + 1] = os.path.basename(r["jpegPath"])  # image_id = frameId+1
    return m


def main(cap):
    z = np.load(f"{E13}/analysis/step1_cache_{cap}.npz")
    xyz = z["xyz"]
    d = json.load(open(f"{E13}/analysis/settlement_{cap}_thr0.5.json"))
    kills = d["kills"]
    images = read_images_bin_full(f"{OFF_RUN[cap]}/images.bin")
    cams = read_cameras_bin(f"{OFF_RUN[cap]}/cameras.bin")
    fmap = load_frame_map(cap)

    # rebuild loser observation lists from step1 cache
    obs_pt, obs_iid, obs_kp = z["obs_pt"], z["obs_iid"], z["obs_kp"]

    def first_obs(p, need_photo=False):
        idxs = np.flatnonzero(obs_pt == p)
        for idx in idxs:
            iid = int(obs_iid[idx])
            if not need_photo or os.path.exists(f"{PHOTOS[cap]}/{fmap.get(iid, '?')}"):
                return iid, int(obs_kp[idx])
        return None, None

    def project(iid, X):
        im = images[iid]
        R = qvec2rot(im["qvec"] / np.linalg.norm(im["qvec"]))
        xc = R @ X + im["tvec"]
        f, cx, cy = cams[im["camera_id"]]["params"]
        if xc[2] <= 0:
            return None
        return (f * xc[0] / xc[2] + cx, f * xc[1] / xc[2] + cy)

    suspects = [k for k in kills if -7.5 <= k["fh_L_mm"] < 12.5 and abs(k["fh_W_mm"] - k["fh_L_mm"]) > 15]
    rng = np.random.default_rng(13)
    rand = [kills[i] for i in rng.choice(len(kills), size=min(36, len(kills)), replace=False)]

    def render(sel, name):
        rows = math.ceil(len(sel) / COLS)
        canvas = Image.new("RGB", (COLS * TILE, rows * (TILE + 26)), (18, 18, 18))
        dr = ImageDraw.Draw(canvas)
        recs = []
        skipped = 0
        for i, k in enumerate(sel):
            L, W = k["loser"], k["winner"]
            iid, kp = first_obs(L, need_photo=True)
            if iid is None:
                skipped += 1
                recs.append({"loser": L, "winner": W, "skipped": "no photo on any obs frame (24 missing photos, cap51 slot-overwrite era)"})
                continue
            oxy = images[iid]["xys"][kp]
            photo = f"{PHOTOS[cap]}/{fmap[iid]}"
            im = Image.open(photo)
            x0 = int(np.clip(oxy[0] - TILE / 2, 0, im.width - TILE))
            y0 = int(np.clip(oxy[1] - TILE / 2, 0, im.height - TILE))
            crop = im.crop((x0, y0, x0 + TILE, y0 + TILE))
            cx0, cy0 = (i % COLS) * TILE, (i // COLS) * (TILE + 26)
            canvas.paste(crop, (cx0, cy0))
            cd = ImageDraw.Draw(canvas)
            lx, ly = oxy[0] - x0 + cx0, oxy[1] - y0 + cy0
            cd.ellipse([lx - 9, ly - 9, lx + 9, ly + 9], outline=(255, 40, 40), width=3)
            pw = project(iid, xyz[W])
            dpx = None
            if pw is not None:
                wx, wy = pw[0] - x0 + cx0, pw[1] - y0 + cy0
                cd.line([wx - 8, wy, wx + 8, wy], fill=(40, 255, 60), width=3)
                cd.line([wx, wy - 8, wx, wy + 8], fill=(40, 255, 60), width=3)
                dpx = round(math.hypot(pw[0] - oxy[0], pw[1] - oxy[1]), 1)
            d3 = round(float(np.linalg.norm(xyz[L] - xyz[W])) * 1000, 1)
            cd.text((cx0 + 4, cy0 + TILE + 3),
                    f"L{L} fhL{k['fh_L_mm']:.0f} fhW{k['fh_W_mm']:.0f}mm d3D{d3}mm dpx{dpx} aL{k['ang_L']:.1f} aW{k['ang_W']:.1f}",
                    fill=(230, 230, 230))
            recs.append({"loser": L, "winner": W, "frame": fmap[iid], "obs_xy": [round(float(oxy[0]), 1), round(float(oxy[1]), 1)],
                         "winner_reproj_px_at_loser_obs": dpx, "dist3d_mm": d3,
                         "fh_L_mm": k["fh_L_mm"], "fh_W_mm": k["fh_W_mm"]})
        canvas.save(f"{E13}/analysis/kill_audit_{name}_{cap}.png")
        if skipped:
            print(f"  [{name}] skipped {skipped} samples without photos")
        return recs

    out = {"suspects": render(suspects, "suspects"), "random36": render(rand, "random")}
    # aggregate: winner-projection distance stats over ALL kills (not just sampled)
    dall = []
    d3all = []
    for k in kills:
        iid, kp = first_obs(k["loser"])
        if iid is not None:
            pw = project(iid, xyz[k["winner"]])
            if pw is not None:
                oxy = images[iid]["xys"][kp]
                dall.append(math.hypot(pw[0] - oxy[0], pw[1] - oxy[1]))
        d3all.append(float(np.linalg.norm(xyz[k["loser"]] - xyz[k["winner"]])))
    out["all_kills_winner_reproj_px"] = {"p50": round(float(np.median(dall)), 2),
                                         "p90": round(float(np.percentile(dall, 90)), 2)}
    out["all_kills_3d_dist_mm"] = {"p50": round(float(np.median(d3all)) * 1000, 1),
                                   "p90": round(float(np.percentile(d3all, 90)) * 1000, 1)}
    json.dump(out, open(f"{E13}/analysis/kill_audit_{cap}.json", "w"), indent=1)
    print(cap, "suspects:", len(suspects), "audit:", out["all_kills_winner_reproj_px"], out["all_kills_3d_dist_mm"])


if __name__ == "__main__":
    for cap in ("cap51", "cap50"):
        main(cap)
