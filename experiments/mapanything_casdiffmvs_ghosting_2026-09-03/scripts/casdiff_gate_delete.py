"""Port CasDiffMVS's STRICT geometric gate and its depth averaging onto
MapAnything's depths, deleting nothing.

Why: CasDiffMVS's output is thin (5.4 mm, zero split) not only because its
fusion deletes ~35% of pixels, but because every surviving pixel's depth is
REPLACED by the average of its own depth and the reprojected depths of all
source views that passed a strict test (reprojection < 1 px AND relative depth
difference < 1%, filter.py:98). Its points are consensus points; MapAnything's
are 132 independent opinions.

An earlier consensus attempt used MapAnything's own 2%/2% test over ~50
partners and the user judged it worse -- a loose gate averages things that
should not be averaged. This ports the strict gate verbatim.

Faithfulness:
  - `check_geometric_consistency` is IMPORTED from the upstream repo, not
    rewritten, so the criterion is the same code CasDiffMVS runs.
  - The averaging is the official line filter.py:190
        depth_est_averaged = (sum(all_srcview_depth_ests) + ref_depth_est) / (geo_mask_sum + 1)
    Inconsistent reprojections are already zeroed inside the official function,
    so a pixel with zero consistent views keeps its own depth exactly. The
    formula degrades gracefully; no threshold and therefore no seam.
  - Source views come from the official pair.txt (num_view=10 -> 9 sources),
    mapped from CasDiffMVS source indices to MapAnything frames.

Deliberate deviations, both stated:
  1. The official `geo_mask_sum >= 3` step is DROPPED -- that is the deletion
     step, and nothing may be deleted here.
  2. The official depth-range gate (mask2) uses the COLMAP cam file range,
     which is narrower than MapAnything's depth spread; a per-view [p0.05,
     p99.95] range is used instead so the range gate does not silently do the
     gating that the 1px/1% test is supposed to do.
"""
import argparse, hashlib, json, sys, time
from pathlib import Path
import numpy as np
import open3d as o3d
import torch
from PIL import Image as PILImage

sys.path.insert(0, "/root/map-anything-official-exact-src-20260902"); sys.path.insert(0, "/root")
from mapanything.utils.colmap import qvec2rotmat, read_model
from mapanything.utils.geometry import closed_form_pose_inverse
from mapanything.utils.image import preprocess_inputs
from mapanything.utils.wai.camera import rotate_pinhole_90degcw
from mapanything_prepare_upright_colmap import rotate_world_to_camera
sys.path.insert(0, "/root/casdiffmvs_official_20260903/diffmvs_upstream")
from filter import check_geometric_consistency   # official criterion, imported not rewritten

ap = argparse.ArgumentParser()
ap.add_argument("--saved", default="/root/mapanything_layer_audit_A_imgs132_up_20260903")
ap.add_argument("--images", default="/root/imgs132_up")
ap.add_argument("--colmap_sparse", default="/root/mapanything_apache_production_sparse_colmap_20260903/input/sparse")
ap.add_argument("--mapping", default="/root/mapanything_apache_images_only_capture_order_20260903/capture_order_source_to_frame.json")
ap.add_argument("--pair", default="/root/casdiffmvs_official_20260903/mvs_P16k/pair.txt")
ap.add_argument("--start_depth", required=True)
ap.add_argument("--out_dir", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--num_src", type=int, default=9, help="official num_view=10 -> 9 sources")
ap.add_argument("--geo_pixel_thres", type=float, default=1.0)
ap.add_argument("--geo_depth_thres", type=float, default=0.01)
ap.add_argument("--passes", type=int, default=1)
ap.add_argument("--export", action="store_true")
ap.add_argument("--delete", action="store_true", help="apply the official geo_mask_sum >= thres deletion; pixels failing it are dropped on export")
ap.add_argument("--geo_mask_thres", type=int, default=3)
ap.add_argument("--no_average", action="store_true", help="compute the gate but leave the depth untouched (skip the official averaging)")
a = ap.parse_args()
t0 = time.time()
out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

info = json.load(open(f"{a.saved}/info.json")); names = [m["name"] for m in info["image_manifest"]]
mask = np.load(f"{a.saved}/mask.npy")[..., 0].astype(bool)
nam = np.load(f"{a.saved}/non_ambiguous_mask.npy").astype(bool)
if nam.ndim == 4: nam = nam[..., 0]
rgb = np.load(f"{a.saved}/img_no_norm.npy")
depth = np.load(a.start_depth).astype(np.float64)
V, H, W = depth.shape
valid = mask & nam & (depth > 0)

cams, imgs, _ = read_model(a.colmap_sparse, ext=".bin")
by = {im.name: im for im in imgs.values()}
rv = []
for n in names:
    im = by[n]; cam = cams[im.camera_id]
    fx, fy, cx, cy = cam.params
    _, _, fxu, fyu, cxu, cyu = rotate_pinhole_90degcw(cam.width, cam.height, fx, fy, cx, cy)
    sc = 1500.0 / 3024.0
    K15 = np.array([[fxu*sc,0,cxu*sc],[0,fyu*sc,cyu*sc],[0,0,1]], dtype=np.float32)
    R, t = rotate_world_to_camera(qvec2rotmat(im.qvec), im.tvec)
    w2c = np.eye(4); w2c[:3,:3] = R; w2c[:3,3] = t
    c2w = closed_form_pose_inverse(w2c[None])[0].astype(np.float32)
    pil = PILImage.open(f"{a.images}/{n}").convert("RGB")
    rv.append({"img": torch.from_numpy(np.asarray(pil, dtype=np.uint8).copy()), "intrinsics": torch.from_numpy(K15), "camera_poses": torch.from_numpy(c2w), "is_metric_scale": torch.tensor([False])})
proc = preprocess_inputs(rv)
K = np.stack([v["intrinsics"][0].numpy().astype(np.float64) for v in proc])
C2W = np.stack([v["camera_poses"][0].numpy().astype(np.float64) for v in proc])
EXT = np.stack([np.linalg.inv(C2W[i]) for i in range(V)])   # world2cam, COLMAP convention

s2f = json.load(open(a.mapping))          # source index -> MapAnything frame
lines = open(a.pair).read().split()
n_pair = int(lines[0]); p = 1
pairs = {}
for _ in range(n_pair):
    ref_s = int(lines[p]); p += 1
    k = int(lines[p]); p += 1
    src = []
    for j in range(k):
        src.append(int(lines[p])); p += 2
    pairs[ref_s] = src
print(f"pair.txt: {n_pair} refs, first ref has {len(pairs[0])} sources", flush=True)

stats = []
gate = np.zeros(valid.shape, dtype=bool)   # per-view: passed the official >= thres test on the LAST pass
for it in range(a.passes):
    new_depth = depth.copy()
    gm_all = []
    for ref_s, src_s in pairs.items():
        f = int(s2f[ref_s])
        dref = depth[f]
        dmin = float(np.percentile(dref[valid[f]], 0.05)); dmax = float(np.percentile(dref[valid[f]], 99.95))
        acc = np.zeros_like(dref); gsum = np.zeros(dref.shape, np.int32)
        for s in src_s[: a.num_src]:
            j = int(s2f[int(s)])
            gmask, drep, _, _ = check_geometric_consistency(
                dref, K[f], EXT[f], depth[j], K[j], EXT[j], dmax, dmin,
                a.geo_pixel_thres, a.geo_depth_thres)
            gmask = gmask & valid[f] & (depth[j] > 0).any() if False else gmask
            gsum += gmask.astype(np.int32)
            acc += drep
        avg = (acc + dref) / (gsum + 1)          # official filter.py:190, no deletion
        new_depth[f] = depth[f] if a.no_average else np.where(valid[f], avg, 0.0)
        gm_all.append(float((gsum >= a.geo_mask_thres)[valid[f]].mean()))
        gate[f] = valid[f] & (gsum >= a.geo_mask_thres)
    ch = np.abs(new_depth - depth)[valid] / np.maximum(depth[valid], 1e-6)
    stats.append({"pass": it, "geo_ge3_frac_p50": float(np.median(gm_all)),
                  "rel_change_p50": float(np.median(ch)), "rel_change_p95": float(np.percentile(ch, 95))})
    print("pass", it, stats[-1], flush=True)
    depth = new_depth

np.save(out / "depth_native_final.npy", depth.astype(np.float32))
np.save(out / "gate_keep.npy", gate)
print(f"gate: {int(gate.sum()):,} of {int(valid.sum()):,} valid pixels pass >= {a.geo_mask_thres} views ({100*gate.sum()/max(valid.sum(),1):.1f}%)", flush=True)
res = {"tag": a.tag, "purpose": "CasDiffMVS strict gate (imported check_geometric_consistency, 1px/1%) + official averaging filter.py:190 applied to MapAnything depths; deletion step " + ("APPLIED (official geo_mask_sum >= thres)" if a.delete else "dropped so nothing is removed") + "",
       "delete": a.delete, "geo_mask_thres": a.geo_mask_thres,
       "start_depth": a.start_depth, "num_src": a.num_src, "geo_pixel_thres": a.geo_pixel_thres,
       "geo_depth_thres": a.geo_depth_thres, "passes": a.passes, "stats": stats, "seconds": time.time()-t0}
if a.export:
    xyz, col = [], []
    for f in range(V):
        keepf = (valid[f] & gate[f]) if a.delete else valid[f]
        yy, xx = np.nonzero(keepf)
        z = depth[f][yy, xx]
        x = (xx - K[f][0,2]) / K[f][0,0] * z
        y = (yy - K[f][1,2]) / K[f][1,1] * z
        pc = np.stack([x,y,z,np.ones_like(z)],1)
        xyz.append((C2W[f] @ pc.T).T[:, :3].astype(np.float32)); col.append(rgb[f][keepf])
    xyz = np.concatenate(xyz); col = np.concatenate(col)
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(xyz.astype(np.float64))
    pcd.colors = o3d.utility.Vector3dVector(col.astype(np.float64)/255.0)
    ply = out / f"mapanything_{a.tag}.ply"
    o3d.io.write_point_cloud(str(ply), pcd, write_ascii=False, compressed=False)
    h = hashlib.sha256()
    with open(ply,"rb") as fh:
        while c := fh.read(8*1024*1024): h.update(c)
    res["points"] = int(xyz.shape[0]); res["ply"] = {"path": str(ply), "bytes": ply.stat().st_size, "sha256": h.hexdigest()}
(out / "result.json").write_text(json.dumps(res, indent=2)+"\n")
print(json.dumps({k:v for k,v in res.items() if k!="stats"}, indent=2))
