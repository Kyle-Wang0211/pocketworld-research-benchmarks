#!/usr/bin/env python3
"""A ruler calibrated against the user's own visual verdicts, not a
self-consistency score.

The official multi-view confidence is gameable by smoothing (user rejected the
version that scored best on it), so this measures two things it cannot see:

  A. QUANTISATION / FACETING  -- fraction of adjacent valid pixel pairs whose
     depth difference is essentially zero, and the fraction of 7x7 windows on
     smooth regions containing very few distinct depth values. Per-pixel
     averaging with nearest-neighbour partner sampling collapses many pixels
     onto identical values, producing stair-step facets that read as layering
     to the eye.
  B. SEPARATED LAYERS (real ghosting) -- for each reference view, project all
     other views' surface points into it; per pixel, look at the distances of
     the points landing there and detect a SECOND mode separated from the first
     by more than max(abs_gap, rel_gap * z) carrying at least min_mass of the
     samples. Merging two layers reduces this; smoothing within one layer does
     not change it.

Both are reported per depth-map set so different candidates can be ordered, and
the ordering is checked against the verdicts already given by the user."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from einops import einsum
from PIL import Image as PILImage

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/root")
from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import closed_form_pose_inverse, depthmap_to_camera_frame  # noqa: E402
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.multiview_confidence import _in_image, _project_pts3d_to_image_with_depth  # noqa: E402
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import rotate_world_to_camera  # noqa: E402


def q_(v):
    v = np.asarray(v, dtype=np.float64).reshape(-1)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return {"n": 0}
    return {"n": int(v.size), "p05": float(np.percentile(v, 5)), "p50": float(np.median(v)), "p95": float(np.percentile(v, 95))}


def facet_stats(z, valid):
    """A: quantisation / stair-stepping."""
    out = {}
    dx = z[:, 1:] - z[:, :-1]
    mx = valid[:, 1:] & valid[:, :-1]
    dy = z[1:, :] - z[:-1, :]
    my = valid[1:, :] & valid[:-1, :]
    zx = z[:, 1:][mx].clamp_min(1e-6)
    zy = z[1:, :][my].clamp_min(1e-6)
    rel = torch.cat([(dx[mx].abs() / zx), (dy[my].abs() / zy)])
    out["adj_rel_diff_exact_zero_frac"] = float((rel == 0).float().mean())
    out["adj_rel_diff_below_1e5_frac"] = float((rel < 1e-5).float().mean())
    out["adj_rel_diff_p50"] = float(rel.median())
    # distinct values inside 7x7 windows, on windows that are fully valid
    k = 7
    zz = z[None, None]
    vv = valid[None, None].float()
    ones = torch.ones(1, 1, k, k, device=z.device)
    cnt = F.conv2d(vv, ones, padding=k // 2)
    full = (cnt[0, 0] >= k * k - 0.5)
    if full.any():
        patches = F.unfold(zz, kernel_size=k, padding=k // 2)[0]  # (k*k, HW)
        sel = full.reshape(-1).nonzero(as_tuple=True)[0]
        sel = sel[torch.randperm(sel.numel(), device=z.device)[:20000]]
        p = patches[:, sel]
        # count distinct at 1e-6 relative resolution
        pr = torch.round(p / p.mean(0, keepdim=True).clamp_min(1e-9) * 1e6)
        # distinct count per column without a Python loop: sort then count changes
        srt, _ = torch.sort(pr, dim=0)
        distinct = (1 + (srt[1:] != srt[:-1]).sum(0)).float()
        out["distinct_values_per_7x7_p50"] = float(distinct.median())
        out["frac_windows_under_10_distinct"] = float((distinct < 10).float().mean())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
    ap.add_argument("--images", default="/root/imgs132_up")
    ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
    ap.add_argument("--sets", nargs="+", required=True, help="name=path.npy (depth (V,H,W)) ; 'base' allowed for the affine MapAnything")
    ap.add_argument("--out", required=True)
    ap.add_argument("--views", type=int, default=24, help="reference views to probe for layer separation")
    ap.add_argument("--abs_gap", type=float, default=0.02)
    ap.add_argument("--rel_gap", type=float, default=0.01)
    ap.add_argument("--min_mass", type=float, default=0.15)
    ap.add_argument("--partners", type=int, default=24)
    args = ap.parse_args()
    t0 = time.time()
    dev = "cuda"

    saved = Path(args.saved)
    info = json.load(open(saved / "info.json"))
    names = [m["name"] for m in info["image_manifest"]]
    mask = np.load(saved / "mask.npy")[..., 0].astype(bool)
    nam = np.load(saved / "non_ambiguous_mask.npy").astype(bool)
    if nam.ndim == 4:
        nam = nam[..., 0]
    V, H, W = mask.shape

    cams, imgs, _ = read_model(args.colmap_sparse, ext=".bin")
    by_name = {im.name: im for im in imgs.values()}
    ref_views = []
    for n in names:
        im = by_name[n]
        cam = cams[im.camera_id]
        fx, fy, cx, cy = cam.params
        _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
        sc = 1500.0 / 3024.0
        K15 = np.array([[fxu * sc, 0, cxu * sc], [0, fyu * sc, cyu * sc], [0, 0, 1]], dtype=np.float32)
        R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
        w2c = np.eye(4); w2c[:3, :3] = R; w2c[:3, 3] = t
        c2w = closed_form_pose_inverse(w2c[None])[0].astype(np.float32)
        pil = PILImage.open(Path(args.images) / n).convert("RGB")
        ref_views.append({"img": torch.from_numpy(np.asarray(pil, dtype=np.uint8)), "intrinsics": torch.from_numpy(K15), "camera_poses": torch.from_numpy(c2w), "is_metric_scale": torch.tensor([False])})
    proc = preprocess_inputs(ref_views)
    Kt = torch.stack([v["intrinsics"][0] for v in proc]).to(dev)
    Pt = torch.stack([v["camera_poses"][0] for v in proc]).to(dev)
    W2C = closed_form_pose_inverse(Pt)

    report = {"abs_gap": args.abs_gap, "rel_gap": args.rel_gap, "min_mass": args.min_mass, "sets": {}}
    probe = list(range(0, V, max(1, V // args.views)))[: args.views]
    for spec in args.sets:
        name, path = spec.split("=", 1)
        d = np.load(path).astype(np.float32)
        assert d.shape == (V, H, W), (name, d.shape)
        depth = torch.from_numpy(d).to(dev)
        valid = torch.from_numpy(mask & nam).to(dev) & (depth > 0)
        # A: faceting
        fac = [facet_stats(depth[i], valid[i]) for i in probe]
        A = {k: q_([f[k] for f in fac if k in f]) for k in fac[0]}
        # B: separated layers
        secmode, gapmed = [], []
        for i in probe:
            # bucket partner points by pixel, keep min & the largest separated mode
            first = torch.full((H, W), float("inf"), device=dev)
            cnt = torch.zeros(H, W, device=dev)
            # two passes: pass1 nearest surface, pass2 mass beyond a gap
            js = [j for j in range(V) if j != i][: args.partners * 4 : 4][: args.partners]
            samples_near = torch.zeros(H, W, device=dev)
            samples_far = torch.zeros(H, W, device=dev)
            for rep in range(2):
                for j in js:
                    pts_cam, _ = depthmap_to_camera_frame(depth[j][None], Kt[j][None])
                    homo = torch.cat([pts_cam[0], torch.ones_like(pts_cam[0][..., :1])], -1)
                    Xw = einsum(Pt[j], homo, "a b, ... b -> ... a")[..., :3]
                    homo2 = torch.cat([Xw, torch.ones_like(Xw[..., :1])], -1)
                    Xi = einsum(W2C[i], homo2, "a b, ... b -> ... a")[..., :3]
                    proj = _project_pts3d_to_image_with_depth(Xi[None], Kt[i][None])[0]
                    ok = _in_image(proj, H, W, min_depth=0.04) & valid[j]
                    if not ok.any():
                        continue
                    xy = proj[..., :2][ok].round().long()
                    zz = proj[..., 2][ok]
                    lin = (xy[:, 1].clamp(0, H - 1) * W + xy[:, 0].clamp(0, W - 1))
                    if rep == 0:
                        f = first.reshape(-1)
                        f.scatter_reduce_(0, lin, zz, reduce="amin")
                    else:
                        fz = first.reshape(-1)[lin]
                        thr = fz + torch.maximum(torch.full_like(fz, args.abs_gap), args.rel_gap * fz)
                        near = zz <= thr
                        samples_near.reshape(-1).scatter_add_(0, lin[near], torch.ones_like(zz[near]))
                        samples_far.reshape(-1).scatter_add_(0, lin[~near], torch.ones_like(zz[~near]))
            tot = samples_near + samples_far
            has = (tot >= 4) & valid[i]
            if has.any():
                frac_far = samples_far[has] / tot[has]
                secmode.append(float((frac_far >= args.min_mass).float().mean()))
                gapmed.append(float(frac_far.median()))
        B = {"pixels_with_separated_second_layer_frac": q_(secmode), "median_far_mass_frac": q_(gapmed)}
        report["sets"][name] = {"faceting": A, "separated_layers": B, "path": path}
        print(name, "| faceting zero-diff p50", round(A["adj_rel_diff_exact_zero_frac"]["p50"], 4),
              "| <1e-5 p50", round(A["adj_rel_diff_below_1e5_frac"]["p50"], 4),
              "| distinct/7x7 p50", round(A.get("distinct_values_per_7x7_p50", {}).get("p50", float("nan")), 1),
              "| 2nd-layer frac p50", round(B["pixels_with_separated_second_layer_frac"]["p50"], 4), flush=True)
    report["seconds"] = time.time() - t0
    Path(args.out).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: {kk: {k3: round(v3["p50"], 5) for k3, v3 in vv.items()} for kk, vv in v.items() if kk != "path"} for k, v in report["sets"].items()}, indent=2))


if __name__ == "__main__":
    main()
