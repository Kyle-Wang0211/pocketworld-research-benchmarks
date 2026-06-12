#!/usr/bin/env python3
"""Experiment AA: controlled window-angular-span sweep at fixed content.

User question (2026-06-12): "你怎么保证32°是最完美的呢？你测试过其他角度吗" —
the icosa42 face-window span (~63°) and the freq-3 1-ring span (~40°) were
both design extrapolations, never measured. Observational evidence says all
high-conf windows live at 20-60° span, but content confounds it.

This experiment removes the confound: fix the window CENTER (= content) at
the centroid of a known easy window, vary only the cap diameter, sample 18
frames per cap with farthest-point sampling, run the full K18@896 oracle,
and read conf median. Two centers: win025 (true 11.81) and win040 (10.55).

Results append to expAA_cap_span_sweep.jsonl per diameter (crash-proof).
"""

import json
import os
import sys
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
OUT = O / "expAA_cap_span_sweep.jsonl"

man = json.loads((O / "k414_spatial_order_manifest.json").read_text())["frames"]
bundle = json.loads((D / "capture_seq_k35_strict/photo_bundle.json").read_text())
azel = {fr["highresFilename"]: (fr["azimuth"], fr["elevation"]) for fr in bundle["frames"]}


def unit(az: float, el: float) -> np.ndarray:
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
    imgs_cpu, ex_pre, in_pre = model._preprocess_inputs(paths, ext, ixt, 896, "upper_bound_resize")
    imgs, ex_t, in_t = model._prepare_model_inputs(imgs_cpu, ex_pre, in_pre)
    ex_norm = model._normalize_extrinsics(ex_t.clone())
    raw = model._run_model_forward(
        imgs, ex_norm, in_t,
        export_feat_layers=[], infer_gs=False, use_ray_pose=False,
        ref_view_strategy="saddle_balanced",
    )
    pred = model._convert_to_prediction(raw)
    return float(np.median(np.asarray(pred.conf)))


def fps18(cand_idx, center) -> list:
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
    if done:
        print(f"resume: {len(done)} combos already on disk, skipping them", flush=True)
    for tag, w in [("c25", 25), ("c40", 40)]:
        sub_idx = list(range(w * 9, w * 9 + 18))
        center = dirs[sub_idx].mean(axis=0)
        center /= np.linalg.norm(center)
        for diam in [20, 30, 40, 55, 70, 85]:
            if (tag, diam) in done:
                continue
            cosr = np.cos(np.radians(diam / 2))
            cand = np.where(dirs @ center >= cosr)[0]
            row = {"center": tag, "diam": diam, "n_avail": int(len(cand))}
            if len(cand) < 18:
                row["conf"] = None
                print(f"{tag} diam{diam}deg: only {len(cand)} frames, skip", flush=True)
            else:
                pick = fps18(list(cand), center)
                us = dirs[pick]
                row["achieved_span"] = float(
                    np.degrees(np.arccos(np.clip((us @ us.T).min(), -1, 1)))
                )
                row["conf"] = run_k18([frames[i] for i in pick])
                print(
                    f"{tag} diam{diam}deg: avail {len(cand)}, "
                    f"achieved {row['achieved_span']:.1f}deg, conf {row['conf']:.2f}",
                    flush=True,
                )
            with OUT.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
    print("EXPAA-DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
