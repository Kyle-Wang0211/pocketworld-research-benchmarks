#!/usr/bin/env python3
"""Solve one depth-correction field per view from cross-view agreement alone.

What the measurements say, in order:

  radial       flat (outer/inner 0.986)  -- not the focal artefact
  spatial      74% of the std survives a 64x64 block average -- a smooth field,
               not pixel noise
  order        a quartic per view explains only 43% -- smooth but not low-order,
               structure around 64-128 px
  loops        r(v,w) + r(w,x) + r(x,v) has RMS 0.65% against 1.81% per leg, so
               95.7% of the disagreement IS one field per view
  observations the outer 70% is seen by 36 views at the median, not by two

Together those say the disagreement is solvable and, at a control spacing of
~32 px with 36 views voting on every surface, over-determined by orders of
magnitude. That is the difference between this and every field solved earlier
today: those were driven by COLMAP sparse anchors, which only exist in the inner
30%, so in the outer 70% the field was whatever the smoothness prior invented --
which is precisely where the bending appeared.

Here every correspondence is a constraint, the outer 70% included. The residual
is exact rather than assumed: scaling view v's depth by exp(g) changes the depth
seen from w by a factor whose log-derivative is (z' - A)/z', with A the depth of
v's optical centre in w, so

    r = [log z' - log d_w] + c * g_v(pixel in v) - g_w(pixel in w)

The gauge -- the global shape that cross-view agreement alone cannot pin down --
is fixed by a weak pull toward zero, i.e. toward the anchored cloud, so the
solution cannot drift into a differently-shaped room.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import open3d as o3d
import torch
import torch.nn.functional as F
from PIL import Image as PILImage

sys.path.insert(0, os.getcwd())
sys.path.insert(0, "/root")
from mapanything.utils.colmap import qvec2rotmat, read_model  # noqa: E402
from mapanything.utils.geometry import closed_form_pose_inverse  # noqa: E402
from mapanything.utils.image import preprocess_inputs  # noqa: E402
from mapanything.utils.wai.camera import rotate_pinhole_90degcw  # noqa: E402
from mapanything_prepare_upright_colmap import rotate_world_to_camera  # noqa: E402


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def build_ref_cameras(names, images_dir, colmap_sparse):
    """Same recipe as export_native_anchored.py, so the frame matches exactly."""
    cams, imgs, _ = read_model(colmap_sparse, ext=".bin")
    by_name = {im.name: im for im in imgs.values()}
    views = []
    for n in names:
        im = by_name[n]
        cam = cams[im.camera_id]
        fx, fy, cx, cy = cam.params
        _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
        s = 1500.0 / 3024.0
        K15 = np.array([[fxu * s, 0, cxu * s], [0, fyu * s, cyu * s], [0, 0, 1]], dtype=np.float32)
        R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
        w2c = np.eye(4)
        w2c[:3, :3] = R
        w2c[:3, 3] = t
        c2w = closed_form_pose_inverse(w2c[None])[0].astype(np.float32)
        pil = PILImage.open(Path(images_dir) / n).convert("RGB")
        views.append({"img": torch.from_numpy(np.asarray(pil, dtype=np.uint8)),
                      "intrinsics": torch.from_numpy(K15), "camera_poses": torch.from_numpy(c2w),
                      "is_metric_scale": torch.tensor([False])})
    proc = preprocess_inputs(views)
    K = np.stack([v["intrinsics"][0].numpy().astype(np.float64) for v in proc])
    P = np.stack([v["camera_poses"][0].numpy().astype(np.float64) for v in proc])
    return K, P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
    ap.add_argument("--images", default="/root/imgs132_up")
    ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
    ap.add_argument("--depth", default="/root/mapanything_native_anchored_20260903/depth_native_final.npy")
    ap.add_argument("--out_dir", required=True)
    ap.add_argument("--tag", default="crossview")
    ap.add_argument("--neighbours", type=int, default=8)
    ap.add_argument("--holdout", type=int, default=8,
                    help="further neighbours kept out of the solve entirely; the field is only "
                         "trustworthy if the disagreement drops on these too")
    ap.add_argument("--stride", type=int, default=3)
    ap.add_argument("--grid", type=int, default=32, help="control point spacing in pixels")
    ap.add_argument("--tol", type=float, default=0.10)
    ap.add_argument("--lam", type=float, default=1.0, help="smoothness of each view's field")
    ap.add_argument("--eps", type=float, default=1e-3, help="pull toward the anchored solution; fixes the gauge")
    ap.add_argument("--iters", type=int, default=400)
    ap.add_argument("--highpass", type=float, default=0.0,
                    help="pixels; drop the field's coarser-than-this component before applying it, "
                         "so the cloud keeps the anchored version's overall shape exactly")
    args = ap.parse_args()
    t0 = time.time()
    dev = "cuda"
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    saved = Path(args.saved)
    info = json.load(open(saved / "info.json"))
    names = [m["name"] for m in info["image_manifest"]]
    depth = np.load(args.depth).astype(np.float32)
    rgb = np.load(saved / "img_no_norm.npy")
    V, H, W = depth.shape
    K, P = build_ref_cameras(names, args.images, args.colmap_sparse)
    print(f"{V} views {H}x{W}; focal {K[0,0,0]:.1f} px", flush=True)

    dt = torch.from_numpy(depth).to(dev)
    valid = dt > 0
    Kt = torch.from_numpy(K).to(dev).float()
    Pt = torch.from_numpy(P).to(dev).float()
    w2c = torch.linalg.inv(Pt)
    Cw = Pt[:, :3, 3]
    dist = torch.cdist(Cw, Cw); dist.fill_diagonal_(float("inf"))
    allnb = dist.topk(args.neighbours + args.holdout, largest=False).indices
    nb, nb_hold = allnb[:, :args.neighbours], allnb[:, args.neighbours:]

    ii, jj = torch.meshgrid(torch.arange(H, device=dev), torch.arange(W, device=dev), indexing="ij")
    ii, jj = ii[::args.stride, ::args.stride].reshape(-1), jj[::args.stride, ::args.stride].reshape(-1)

    def build(neigh, label):
        IV, IW, OBS, CO = [], [], [], []
        for v in range(V):
            z = dt[v][ii, jj]
            ok0 = valid[v][ii, jj]
            x = (jj.float() - Kt[v, 0, 2]) / Kt[v, 0, 0] * z
            y = (ii.float() - Kt[v, 1, 2]) / Kt[v, 1, 1] * z
            Xw = torch.stack([x, y, z], 1) @ Pt[v, :3, :3].T + Pt[v, :3, 3]
            for w in neigh[v].tolist():
                Xc = Xw @ w2c[w, :3, :3].T + w2c[w, :3, 3]
                zp = Xc[:, 2]
                u = (Xc[:, 0] / zp.clamp_min(1e-6) * Kt[w, 0, 0] + Kt[w, 0, 2]).round().long()
                vv = (Xc[:, 1] / zp.clamp_min(1e-6) * Kt[w, 1, 1] + Kt[w, 1, 2]).round().long()
                inb = ok0 & (zp > 1e-3) & (u >= 0) & (u < W) & (vv >= 0) & (vv < H)
                uu, vc = u.clamp(0, W - 1), vv.clamp(0, H - 1)
                dw = dt[w][vc, uu]
                obs = torch.log(zp.clamp_min(1e-6)) - torch.log(dw.clamp_min(1e-6))
                keep = inb & (dw > 0) & (obs.abs() < args.tol)
                if not keep.any():
                    continue
                # exact log-derivative: A is v's optical centre depth in w
                A = (Cw[v] @ w2c[w, :3, :3].T + w2c[w, :3, 3])[2]
                c = ((zp - A) / zp.clamp_min(1e-6))[keep]
                IV.append((v * H + ii[keep]) * W + jj[keep])
                IW.append((w * H + vc[keep]) * W + uu[keep])
                OBS.append(obs[keep].float())
                CO.append(c.float())
        IV, IW, OBS, CO = torch.cat(IV), torch.cat(IW), torch.cat(OBS), torch.cat(CO)
        print(f"  {label}: {OBS.numel():,} correspondences, RMS {float((OBS**2).mean())**0.5*100:.4f} %", flush=True)
        return IV, IW, OBS, CO

    IV, IW, OBS, CO = build(nb, "solve set (neighbours 1-%d)" % args.neighbours)
    HV, HW, HOBS, HCO = build(nb_hold, "held out  (neighbours %d-%d)" % (args.neighbours + 1, args.neighbours + args.holdout))
    M = OBS.numel()

    Gh, Gw = H // args.grid + 1, W // args.grid + 1
    g = torch.zeros(V, 1, Gh, Gw, device=dev, requires_grad=True)
    print(f"control grid {Gh}x{Gw} per view -> {V*Gh*Gw:,} unknowns, {M/(V*Gh*Gw):.0f} constraints each", flush=True)
    opt = torch.optim.LBFGS([g], max_iter=args.iters, history_size=20, tolerance_grad=1e-12,
                            tolerance_change=1e-14, line_search_fn="strong_wolfe")
    hist = []

    def closure():
        opt.zero_grad(set_to_none=True)
        G = F.interpolate(g, size=(H, W), mode="bilinear", align_corners=True).reshape(-1)
        r = OBS + CO * G[IV] - G[IW]
        data = (r ** 2).mean()
        dx = g[:, :, :, 1:] - g[:, :, :, :-1]
        dy = g[:, :, 1:, :] - g[:, :, :-1, :]
        smooth = (dx ** 2).mean() + (dy ** 2).mean()
        prior = (g ** 2).mean()
        loss = data + args.lam * smooth + args.eps * prior
        loss.backward()
        hist.append({"data_rms_pct": float(data.detach()) ** 0.5 * 100,
                     "smooth": float(smooth.detach()), "prior": float(prior.detach())})
        return loss

    opt.step(closure)

    with torch.no_grad():
        Gf = F.interpolate(g, size=(H, W), mode="bilinear", align_corners=True).reshape(-1)
        hold_before = float((HOBS ** 2).mean()) ** 0.5 * 100
        hold_after = float(((HOBS + HCO * Gf[HV] - Gf[HW]) ** 2).mean()) ** 0.5 * 100
    print(f"solve set   {hist[0]['data_rms_pct']:.4f} %  ->  {hist[-1]['data_rms_pct']:.4f} %   "
          f"({len(hist)} evaluations)", flush=True)
    print(f"held out    {hold_before:.4f} %  ->  {hold_after:.4f} %"
          f"   {'GENERALISES' if hold_after < hold_before * 0.98 else 'DOES NOT GENERALISE'}", flush=True)

    # Cross-view agreement cannot pin down the overall shape of the room -- that is
    # its null space -- so part of the solved field may be a drift into a
    # consistently wrong shape rather than a correction. Removing the field's
    # coarse component and re-checking the held-out disagreement separates the two:
    # if agreement survives, the work was done locally and the coarse part was
    # drift, which is exactly the part that would read as a bent wall.
    hp_report = {}
    with torch.no_grad():
        for cut in (0, 16, 32, 64, 128):
            if cut == 0:
                gh = g
            else:
                k = max(3, int(round(cut / args.grid)) * 2 + 1)
                pad = k // 2
                low = F.avg_pool2d(F.pad(g, (pad, pad, pad, pad), mode="replicate"), k, stride=1)
                gh = g - low
            Gh_ = F.interpolate(gh, size=(H, W), mode="bilinear", align_corners=True).reshape(-1)
            hr = float(((HOBS + HCO * Gh_[HV] - Gh_[HW]) ** 2).mean()) ** 0.5 * 100
            sr = float(((OBS + CO * Gh_[IV] - Gh_[IW]) ** 2).mean()) ** 0.5 * 100
            amp = float(gh.abs().median()) * 100
            hp_report[cut] = {"holdout_rms_pct": hr, "solve_rms_pct": sr, "field_abs_p50_pct": amp}
            print("  keep detail finer than %4s px:  held out %.4f %%   solve %.4f %%   field |g| p50 %.3f %%"
                  % (cut if cut else "all", hr, sr, amp), flush=True)
    if args.highpass > 0:
        k = max(3, int(round(args.highpass / args.grid)) * 2 + 1)
        pad = k // 2
        with torch.no_grad():
            g -= F.avg_pool2d(F.pad(g, (pad, pad, pad, pad), mode="replicate"), k, stride=1)
        print(f"applying only detail finer than {args.highpass} px", flush=True)

    with torch.no_grad():
        G = F.interpolate(g, size=(H, W), mode="bilinear", align_corners=True)[:, 0]
        dnew = dt * torch.exp(G)
        rel = (torch.exp(G) - 1.0)[valid]
        print(f"applied depth change: p05 {float(torch.quantile(rel[::37],0.05))*100:+.3f} %  "
              f"p50 {float(rel.median())*100:+.3f} %  p95 {float(torch.quantile(rel[::37],0.95))*100:+.3f} %", flush=True)
        xyz, col = [], []
        for f in range(V):
            m = valid[f]
            vv, uu = torch.nonzero(m, as_tuple=True)
            z = dnew[f][vv, uu].double()
            x = (uu.double() - K[f][0, 2]) / K[f][0, 0] * z
            y = (vv.double() - K[f][1, 2]) / K[f][1, 1] * z
            pc = torch.stack([x, y, z], 1) @ torch.from_numpy(P[f][:3, :3]).to(dev).T + torch.from_numpy(P[f][:3, 3]).to(dev)
            xyz.append(pc.cpu().numpy())
            col.append(rgb[f][m.cpu().numpy()])
    XYZ = np.concatenate(xyz); COL = np.concatenate(col)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(XYZ)
    pcd.colors = o3d.utility.Vector3dVector(COL.astype(np.float64) / 255.0)
    ply = out / f"mapanything_{args.tag}.ply"
    o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
    np.save(out / "depth_crossview.npy", dnew.cpu().numpy())
    np.save(out / "field_g.npy", g.detach().cpu().numpy())
    res = {"tag": args.tag, "views": V, "grid_px": args.grid, "control": [Gh, Gw],
           "unknowns": V * Gh * Gw, "correspondences": int(M),
           "constraints_per_unknown": M / (V * Gh * Gw),
           "lam": args.lam, "eps": args.eps, "neighbours": args.neighbours, "stride": args.stride,
           "disagreement_rms_pct_start": hist[0]["data_rms_pct"],
           "disagreement_rms_pct_end": hist[-1]["data_rms_pct"],
           "holdout_rms_pct_start": hold_before, "holdout_rms_pct_end": hold_after,
           "holdout_variance_removed": 1 - (hold_after / hold_before) ** 2,
           "highpass_px": args.highpass, "highpass_scan": hp_report,
           "points": int(XYZ.shape[0]),
           "ply": {"path": str(ply), "bytes": ply.stat().st_size, "sha256": sha256_file(ply)},
           "seconds": time.time() - t0}
    (out / "result.json").write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
