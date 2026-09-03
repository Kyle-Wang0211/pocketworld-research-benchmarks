#!/usr/bin/env python3
"""Build per-view depth priors for CasDiffMVS from the saved MapAnything outputs.

For CasDiffMVS view s (source index, mvs_P16k naming) the MapAnything frame is
f = source_to_frame[s]. MapAnything depth_z[f] is on the upright 392x518 model
image (a crop/resize of the 1500x2000 upright derivative, which is ROTATE_270 of
the 2000x1500 landscape derivative of the 4032x3024 source). We map it back to
the landscape 768x576 CasDiffMVS working image, then fit a per-view affine
z_cas ~= a * z_map + b on pixels that the official fusion kept
(mask/*_final.png), with a robust (Huber-like IRLS) fit. Output: prior_depth
(768x576 float32) per view + fit statistics. No CasDiffMVS depth is modified
here; this only produces an initialisation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

sys.path.insert(0, "/root/casdiffmvs_official_20260903/diffmvs_upstream")
from datasets.data_io import read_pfm  # noqa: E402


def q(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    v = v[np.isfinite(v)]
    return {"n": int(v.size), "p05": float(np.percentile(v, 5)), "p50": float(np.median(v)), "p95": float(np.percentile(v, 95)), "min": float(v.min()), "max": float(v.max())}


def robust_affine(x, y, iters=8):
    """y ~= a x + b, IRLS with Huber weights on relative residual."""
    w = np.ones_like(x)
    a, b = 1.0, 0.0
    for _ in range(iters):
        A = np.stack([x * w, w], 1)
        sol, *_ = np.linalg.lstsq(A, y * w, rcond=None)
        a, b = float(sol[0]), float(sol[1])
        r = (a * x + b - y) / np.maximum(y, 1e-6)
        s = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-6
        k = 1.345 * s
        w = np.where(np.abs(r) <= k, 1.0, k / np.abs(r))
    r = (a * x + b - y) / np.maximum(y, 1e-6)
    return a, b, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
    ap.add_argument("--cas_out", default="/root/casdiffmvs_official_20260903/out_blendmvg_768x576_nv10")
    ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--W", type=int, default=768)
    ap.add_argument("--H", type=int, default=576)
    ap.add_argument("--conf_dir", default="conf2")
    args = ap.parse_args()
    out = Path(args.out_dir)
    (out / "prior_depth").mkdir(parents=True, exist_ok=True)

    s2f = json.load(open(args.mapping))
    depth_up = np.load(Path(args.saved) / "depth_z.npy")[..., 0].astype(np.float32)  # (V,518,392)
    mask_up = np.load(Path(args.saved) / "mask.npy")[..., 0].astype(bool)
    V, Hm, Wm = depth_up.shape
    assert (Hm, Wm) == (518, 392), (Hm, Wm)
    # model image = crop/resize of the 1500x2000 upright image: scale s, long-axis crop offset
    s = Wm / 1500.0
    off_v = (2000.0 * s - Hm) / 2.0  # ~2.33 px in model space

    stats = []
    for src in range(V):
        f = int(s2f[src])
        d = depth_up[f]
        m = mask_up[f]
        # 1) model 392x518 -> upright 1500x2000 (bilinear, inverse of crop/resize)
        dt = torch.from_numpy(d)[None, None]
        mt = torch.from_numpy(m.astype(np.float32))[None, None]
        # sample positions: for upright pixel (x,y) in 1500x2000 -> model (x*s, y*s - off_v)
        ys, xs = torch.meshgrid(torch.arange(2000, dtype=torch.float32), torch.arange(1500, dtype=torch.float32), indexing="ij")
        gx = (xs + 0.5) * s - 0.5
        gy = (ys + 0.5) * s - off_v - 0.5
        grid = torch.stack([2 * gx / (Wm - 1) - 1, 2 * gy / (Hm - 1) - 1], -1)[None]
        d_up = F.grid_sample(dt, grid, mode="bilinear", align_corners=True, padding_mode="border")[0, 0].numpy()
        m_up = F.grid_sample(mt, grid, mode="nearest", align_corners=True, padding_mode="zeros")[0, 0].numpy() > 0.5
        # 2) upright 1500x2000 -> landscape 2000x1500 (inverse of PIL ROTATE_270 == np.rot90 k=+1)
        d_land = np.ascontiguousarray(np.rot90(d_up, 1))
        m_land = np.ascontiguousarray(np.rot90(m_up, 1))
        assert d_land.shape == (1500, 2000)
        # 3) landscape 2000x1500 -> 768x576 (bilinear)
        d_cas = F.interpolate(torch.from_numpy(d_land)[None, None], size=(args.H, args.W), mode="bilinear", align_corners=False)[0, 0].numpy()
        m_cas = F.interpolate(torch.from_numpy(m_land.astype(np.float32))[None, None], size=(args.H, args.W), mode="nearest")[0, 0].numpy() > 0.5
        # 4) affine fit against CasDiffMVS depth on fusion-kept pixels
        cas = read_pfm(str(Path(args.cas_out) / "depth_est" / f"{src:08d}.pfm"))[0].astype(np.float32)
        final = np.asarray(Image.open(Path(args.cas_out) / "mask" / f"{src:08d}_final.png")) > 0
        conf = read_pfm(str(Path(args.cas_out) / args.conf_dir / f"{src:08d}.pfm"))[0].astype(np.float32)
        if conf.shape != cas.shape:
            conf = F.interpolate(torch.from_numpy(conf)[None, None], size=cas.shape, mode="nearest")[0, 0].numpy()
        sel = final & m_cas & (cas > 0) & (d_cas > 0)
        if sel.sum() < 500:
            stats.append({"src": src, "frame": f, "n_fit": int(sel.sum()), "ok": False})
            continue
        # subsample for speed
        idx = np.flatnonzero(sel)
        if idx.size > 60000:
            idx = np.random.default_rng(src).choice(idx, 60000, replace=False)
        a, b, r = robust_affine(d_cas.reshape(-1)[idx].astype(np.float64), cas.reshape(-1)[idx].astype(np.float64))
        prior = (a * d_cas + b).astype(np.float32)
        prior[~m_cas] = 0.0  # no prior where MapAnything itself masked
        np.save(out / "prior_depth" / f"{src:08d}.npy", prior)
        stats.append({"src": src, "frame": f, "n_fit": int(idx.size), "ok": True, "a": a, "b": b, "rel_resid_p50": float(np.median(np.abs(r))), "rel_resid_p90": float(np.percentile(np.abs(r), 90)), "prior_coverage": float(m_cas.mean()), "cas_final_coverage": float(final.mean())})
        if src % 20 == 0:
            print(f"src {src} frame {f} a={a:.4f} b={b:.4f} |rel resid| p50={np.median(np.abs(r)):.4f} p90={np.percentile(np.abs(r), 90):.4f}", flush=True)
    ok = [t for t in stats if t.get("ok")]
    summary = {"views": V, "fitted": len(ok), "a": q([t["a"] for t in ok]), "b": q([t["b"] for t in ok]), "rel_resid_p50": q([t["rel_resid_p50"] for t in ok]), "rel_resid_p90": q([t["rel_resid_p90"] for t in ok]), "prior_coverage": q([t["prior_coverage"] for t in ok]), "cas_final_coverage": q([t["cas_final_coverage"] for t in ok])}
    (out / "prior_stats.json").write_text(json.dumps({"summary": summary, "per_view": stats}, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
