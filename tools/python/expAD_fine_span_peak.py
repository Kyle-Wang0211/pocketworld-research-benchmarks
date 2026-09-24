#!/usr/bin/env python3
"""expAD: fine span sweep to pin the TRUE conf peak (user 2026-06-13:
"试试35-40度，看看真正的峰值在哪里").

expAA coarse facts: c25 (easy content) flat 26.2-54.6° (12.44-12.53);
c40 (hard content) 38.0°->8.11, 53.5°->6.26 — already -23% at 53.5,
no plateau. Coarse grid can't say where the peak/knee actually sits.

This run: fine cap ladders on BOTH centers, same machinery as expAA
(fixed center = fixed content, FPS-18 in cap, official K18@896,
conf median). Resume-aware JSONL.

  c25 caps: 32,35,38,41,44,47,50  (targets achieved ~28-45°)
  c40 caps: 44,48,52              (fills its 38->53.5 gap; below 40
                                   impossible: cap30 has only 9 frames)
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, "/Users/kaidongwang/Developer/Aether3D-cross/.deps/Depth-Anything-3/src")
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from da3base_official_streaming_oracle import install_mps_chunked_sdpa  # noqa: E402

install_mps_chunked_sdpa(torch, 256, 4.0)

from depth_anything_3.api import DepthAnything3  # noqa: E402

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
OUT = O / "expAD_fine_span_peak.jsonl"

man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
bundle = json.loads((D / "capture_seq_k35_strict/photo_bundle.json").read_text())
azel = {fr["highresFilename"]: (fr["azimuth"], fr["elevation"]) for fr in bundle["frames"]}


def unit(az, el):
    return np.array([np.cos(el) * np.cos(az), np.sin(el), np.cos(el) * np.sin(az)])


frames, dirs = [], []
for r in man:
    fn = r["jpegPath"].split("/")[-1]
    if fn in azel:
        frames.append(r)
        dirs.append(unit(*azel[fn]))
dirs = np.stack(dirs)

model = DepthAnything3.from_pretrained(
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE"
).to(device=torch.device("mps"))
model.model.eval()


def run_k18(sub) -> float:
    paths = [str(D / "capture_seq_k35_strict" / r["jpegPath"]) for r in sub]
    ext = np.stack([np.asarray(r["cameraExtrinsic4x4"], dtype=np.float32).reshape(4, 4) for r in sub])
    ixt = np.stack(
        [
            np.asarray(
                [
                    [r["cameraIntrinsicFxFyCxCy"][0], 0, r["cameraIntrinsicFxFyCxCy"][2]],
                    [0, r["cameraIntrinsicFxFyCxCy"][1], r["cameraIntrinsicFxFyCxCy"][3]],
                    [0, 0, 1],
                ],
                dtype=np.float32,
            )
            for r in sub
        ]
    )
    pred = model.inference(
        paths, extrinsics=ext, intrinsics=ixt,
        align_to_input_ext_scale=True,
        process_res=896, process_res_method="upper_bound_resize",
    )
    return float(np.median(np.asarray(pred.conf)))


def fps18(cand_idx, center):
    d2c = dirs[cand_idx] @ center
    chosen = [int(np.argmax(d2c))]
    while len(chosen) < 18:
        sel = dirs[cand_idx][chosen]
        dmin = (dirs[cand_idx] @ sel.T).max(axis=1)
        dmin[chosen] = 2.0
        chosen.append(int(np.argmin(dmin)))
    return [cand_idx[i] for i in chosen]


def main() -> int:
    done = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            try:
                row = json.loads(line)
                done.add((row["center"], row["diam"]))
            except (json.JSONDecodeError, KeyError):
                continue
    plan = [("c25", 25, d) for d in (32, 35, 38, 41, 44, 47, 50)] + \
           [("c40", 40, d) for d in (44, 48, 52)]
    for tag, w, diam in plan:
        if (tag, diam) in done:
            print(f"[expAD] skip {tag} diam{diam} (cached)", flush=True)
            continue
        sub_idx = list(range(w * 9, w * 9 + 18))
        center = dirs[sub_idx].mean(axis=0)
        center /= np.linalg.norm(center)
        cosr = np.cos(np.radians(diam / 2))
        cand = np.where(dirs @ center >= cosr)[0]
        row = {"center": tag, "diam": diam, "n_avail": int(len(cand))}
        if len(cand) < 18:
            row["conf"] = None
            print(f"[expAD {time.strftime('%H:%M:%S')}] {tag} diam{diam}: only {len(cand)} frames, skip", flush=True)
        else:
            pick = fps18(list(cand), center)
            us = dirs[pick]
            row["achieved_span"] = float(
                np.degrees(np.arccos(np.clip((us @ us.T).min(), -1, 1)))
            )
            t0 = time.time()
            row["conf"] = run_k18([frames[i] for i in pick])
            print(
                f"[expAD {time.strftime('%H:%M:%S')}] {tag} diam{diam}: span {row['achieved_span']:.1f}°, "
                f"conf {row['conf']:.2f} ({time.time()-t0:.0f}s)",
                flush=True,
            )
        with OUT.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
    print("EXPAD-DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
