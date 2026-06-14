#!/usr/bin/env python3
"""expAE: controlled test — does 2D viewpoint spread beat collinear at
EQUAL span? (settles a claim I made without evidence 2026-06-13.)

Per window center, build TWO K18 windows with matched span ~44°:
  - 2D group:        FPS-18 over the cap (natural fill, aspect ~1.5-2)
  - collinear group: 18 frames along the thinnest great-circle band
                     that still spans ~44° (aspect >3, short axis <~10°)
Content (center) + span + inference settings identical -> paired
Δconf = conf(2D) - conf(collinear) isolates arrangement alone.

Waits for expAC (shares the MPS GPU) to finish before loading the
model, to avoid contention / OOM. Resume-aware JSONL.
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

D = Path("data/official_da3_base_k35_strict_seq_2026_06_02")
O = D / "diagnostics/external_pose_k_vs_res_2026_06_10"
OUT = O / "expAE_collinear_vs_2d.jsonl"
EXPAC_LOG = Path("data/expAC_rewindow_span_2026_06_13/expAC_run.log")

TARGET_SPAN = 44.0
SPAN_LO, SPAN_HI = 41.0, 47.0
CAP_2D = 47.0          # FPS-18 over this cap -> span ~44
CAP_POOL = 56.0        # wider pool to find a thin collinear arc
N_CENTERS = 8
COLLINEAR_MAX_SHORT = 12.0   # collinear group short-axis must be <= this
SPREAD_MIN_SHORT = 20.0      # 2D group short-axis must be >= this


def log(m):
    print(f"[expAE {time.strftime('%H:%M:%S')}] {m}", flush=True)


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


def span_of(idx):
    u = dirs[idx]
    return float(np.degrees(np.arccos(np.clip((u @ u.T).min(), -1, 1))))


def tangent(idx, center):
    up = np.array([0, 1.0, 0])
    e1 = np.cross(up, center)
    if np.linalg.norm(e1) < 1e-6:
        e1 = np.cross(np.array([1.0, 0, 0]), center)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(center, e1)
    return np.degrees(np.stack([dirs[idx] @ e1, dirs[idx] @ e2], 1))


def short_axis(idx, center):
    p = tangent(idx, center)
    cov = np.cov(p.T)
    ev = np.sort(np.linalg.eigvalsh(cov))
    return float(2 * np.sqrt(max(ev[0], 0)))      # ~ short-axis extent (1 std *2)


def fps(cand, center, k):
    d2c = dirs[cand] @ center
    chosen = [int(np.argmax(d2c))]
    while len(chosen) < k:
        sel = dirs[cand][chosen]
        dmin = (dirs[cand] @ sel.T).max(axis=1)
        dmin[chosen] = 2.0
        chosen.append(int(np.argmin(dmin)))
    return [cand[i] for i in chosen]


def fps_1d(cand, coord, k):
    chosen = [int(np.argmin(coord)), int(np.argmax(coord))]
    while len(chosen) < k:
        d = np.min(np.abs(coord[:, None] - coord[chosen][None, :]), axis=1)
        d[chosen] = -1
        chosen.append(int(np.argmax(d)))
    return [cand[i] for i in chosen]


def build_2d(center):
    cand = np.where(dirs @ center >= np.cos(np.radians(CAP_2D / 2)))[0]
    if len(cand) < 18:
        return None
    pick = fps(list(cand), center, 18)
    sp = span_of(pick)
    if not (SPAN_LO <= sp <= SPAN_HI):
        return None
    sh = short_axis(pick, center)
    if sh < SPREAD_MIN_SHORT:
        return None
    return {"idx": pick, "span": sp, "short": sh}


def build_collinear(center):
    cand = np.where(dirs @ center >= np.cos(np.radians(CAP_POOL / 2)))[0]
    if len(cand) < 18:
        return None
    p = tangent(cand, center)
    best = None
    for deg in range(0, 180, 5):
        th = np.radians(deg)
        u = np.array([np.cos(th), np.sin(th)])
        uperp = np.array([-np.sin(th), np.cos(th)])
        along = p @ u
        perp = p @ uperp
        for band in (3, 4, 5, 6, 8, 10):
            keep = np.where(np.abs(perp) <= band)[0]
            if len(keep) < 18:
                continue
            if along[keep].max() - along[keep].min() < TARGET_SPAN - 3:
                continue
            pick_local = fps_1d(keep, along[keep], 18)
            pick = [int(cand[i]) for i in pick_local]
            sp = span_of(pick)
            if not (SPAN_LO <= sp <= SPAN_HI):
                continue
            sh = short_axis(pick, center)
            if sh > COLLINEAR_MAX_SHORT:
                continue
            if best is None or sh < best["short"]:
                best = {"idx": pick, "span": sp, "short": sh, "line_deg": deg, "band": band}
            break
    return best


def candidate_centers():
    mean = dirs.mean(axis=0)
    mean /= np.linalg.norm(mean)
    order = [int(np.argmax(dirs @ mean))]
    while len(order) < len(dirs):
        sel = dirs[order]
        dmin = (dirs @ sel.T).max(axis=1)
        dmin[order] = 2.0
        order.append(int(np.argmin(dmin)))
    centers, used = [], []
    for idx in order:
        c = dirs[idx]
        if used and max(cc @ c for cc in used) > np.cos(np.radians(18.0)):
            continue
        used.append(c)
        centers.append(c)
    return centers


def run_k18(model, np_mod, idx):
    sub = [frames[i] for i in idx]
    paths = [str(D / "capture_seq_k35_strict" / r["jpegPath"]) for r in sub]
    ext = np.stack([np.asarray(r["cameraExtrinsic4x4"], np.float32).reshape(4, 4) for r in sub])
    ixt = np.stack([np.asarray(
        [[r["cameraIntrinsicFxFyCxCy"][0], 0, r["cameraIntrinsicFxFyCxCy"][2]],
         [0, r["cameraIntrinsicFxFyCxCy"][1], r["cameraIntrinsicFxFyCxCy"][3]],
         [0, 0, 1]], np.float32) for r in sub])
    pred = model.inference(paths, extrinsics=ext, intrinsics=ixt,
                           align_to_input_ext_scale=True,
                           process_res=896, process_res_method="upper_bound_resize")
    return float(np_mod.median(np_mod.asarray(pred.conf)))


def wait_for_expac():
    deadline = time.time() + 3 * 3600
    while time.time() < deadline:
        if EXPAC_LOG.exists() and "EXPAC-DONE" in EXPAC_LOG.read_text():
            log("expAC done — proceeding")
            return
        time.sleep(60)
    log("expAC wait timed out — proceeding anyway")


def main():
    # ---- select feasible paired centers (no GPU needed) ----
    pairs = []
    for c in candidate_centers():
        g2d = build_2d(c)
        gcol = build_collinear(c)
        if g2d is None or gcol is None:
            continue
        if abs(g2d["span"] - gcol["span"]) > 4:
            continue
        pairs.append((c, g2d, gcol))
        log(f"center {len(pairs)}: 2D span {g2d['span']:.1f}° short {g2d['short']:.1f}° | "
            f"collinear span {gcol['span']:.1f}° short {gcol['short']:.1f}° "
            f"(line {gcol['line_deg']}°)")
        if len(pairs) >= N_CENTERS:
            break
    if len(pairs) < 3:
        log(f"FATAL: only {len(pairs)} feasible paired centers")
        return 1
    log(f"{len(pairs)} feasible paired centers; waiting for GPU …")

    wait_for_expac()

    import torch
    from da3base_official_streaming_oracle import install_mps_chunked_sdpa
    install_mps_chunked_sdpa(torch, 256, 4.0)
    from depth_anything_3.api import DepthAnything3
    model = DepthAnything3.from_pretrained(
        "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_flutter/ios/Runner/Models/DA3-BASE"
    ).to(device=torch.device("mps"))
    model.model.eval()
    log("model ready")

    done = set()
    if OUT.exists():
        for line in OUT.read_text().splitlines():
            try:
                r = json.loads(line)
                if r.get("kind") == "pair":
                    done.add(r["center_i"])
            except (json.JSONDecodeError, KeyError):
                pass

    deltas = []
    for i, (c, g2d, gcol) in enumerate(pairs):
        if i in done:
            continue
        t0 = time.time()
        conf2d = run_k18(model, np, g2d["idx"])
        confcol = run_k18(model, np, gcol["idx"])
        d = conf2d - confcol
        deltas.append(d)
        log(f"center{i}: 2D conf {conf2d:.2f} (span {g2d['span']:.1f}, short {g2d['short']:.1f}) | "
            f"collinear conf {confcol:.2f} (span {gcol['span']:.1f}, short {gcol['short']:.1f}) | "
            f"Δ(2D−col) {d:+.2f}  [{time.time()-t0:.0f}s]")
        with OUT.open("a") as fh:
            fh.write(json.dumps({
                "kind": "pair", "center_i": i,
                "conf_2d": conf2d, "conf_collinear": confcol, "delta": d,
                "span_2d": g2d["span"], "span_col": gcol["span"],
                "short_2d": g2d["short"], "short_col": gcol["short"],
                "line_deg": gcol["line_deg"]}) + "\n")

    if deltas:
        dn = np.asarray(deltas)
        npos = int((dn > 0.2).sum())
        nneg = int((dn < -0.2).sum())
        log(f"SUMMARY: n={len(dn)} | median Δ(2D−col) {np.median(dn):+.2f} | "
            f"mean {dn.mean():+.2f} | 2D-wins {npos} col-wins {nneg} ties {len(dn)-npos-nneg}")
        log("VERDICT: " + ("2D 显著更好" if np.median(dn) > 0.3 and npos >= nneg + 2
                           else "共线显著更好" if np.median(dn) < -0.3 and nneg >= npos + 2
                           else "排布无关（落在噪声底）→ 我之前的 2D 因果是错的"))
        with OUT.open("a") as fh:
            fh.write(json.dumps({"kind": "summary", "n": len(dn),
                                 "median_delta": float(np.median(dn)),
                                 "mean_delta": float(dn.mean()),
                                 "twod_wins": npos, "col_wins": nneg}) + "\n")
    log("EXPAE-DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
