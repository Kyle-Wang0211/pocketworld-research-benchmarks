"""Control for the frame transform: cast layer2F's rays (views 0,33,66,99, same K/pose code as layer2F.py) into the transformed
mesh and into the untransformed mesh; map the first hit back to the CD frame, project into the CD view and compare with that
view's replayed fused depth (final mask). Transformed mesh must agree (small rel. error), untransformed must not."""
import numpy as np, open3d as o3d, json, sys
from replay_lib import *
d = json.load(open("/root/av_ep0_off/scene_dense.sfm")); I = d["intrinsics"][0]; W0 = int(I["width"]); H0 = int(I["height"])
f = float(I["focalLength"]) / float(I["sensorWidth"]) * W0; pp = [float(x) for x in I["principalPoint"]]
poses = {p["poseId"]: p["pose"]["transform"] for p in d["poses"]}; views = sorted([v for v in d["views"] if v["poseId"] in poses], key=lambda v: v["path"])
SW, SH = 336, 250; sca = W0 / SW; fx = f / sca; cx = (W0 / 2 + pp[0]) / sca; cy = (H0 / 2 + pp[1]) / sca
S = json.load(open("sim3_cd2av.json")); s = S["s"]; R = np.array(S["R"]); t = np.array(S["t"])
out = {}
for name, path, inv in [("transformed", sys.argv[1], True), ("untransformed(neg.control)", sys.argv[2], False)]:
    me = o3d.io.read_triangle_mesh(path); scn = o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(me)); del me
    errs = []
    for kk in [0, 33, 66, 99]:
        tr = poses[views[kk]["poseId"]]; Rv = np.array([float(x) for x in tr["rotation"]]).reshape(3, 3, order="F"); C = np.array([float(x) for x in tr["center"]])
        u, v = np.meshgrid(np.arange(SW, dtype=np.float32), np.arange(SH, dtype=np.float32))
        dc = np.stack([(u - cx) / fx, (v - cy) / fx, np.ones_like(u)], -1).reshape(-1, 3); dw = dc @ Rv; dw /= np.linalg.norm(dw, axis=1, keepdims=True)
        th = scn.cast_rays(o3d.core.Tensor(np.concatenate([np.tile(C, (len(dw), 1)), dw], 1).astype(np.float32)))["t_hit"].numpy(); ok = np.isfinite(th)
        P = C + th[ok, None] * dw[ok]
        Pcd = ((R.T @ (P - t).T) / s).T if inv else P      # back to CD frame (for the untransformed mesh P is already "CD" coords)
        o = replay(kk, dict(PAIR_DATA)[kk]); K, E = o["K"].astype(np.float64), o["E"].astype(np.float64)
        Xc = (E[:3, :3] @ Pcd.T).T + E[:3, 3]; uv = (K @ Xc.T).T; uu = uv[:, 0] / uv[:, 2]; vv = uv[:, 1] / uv[:, 2]
        inb = (Xc[:, 2] > 0) & (uu >= 0) & (uu < 767) & (vv >= 0) & (vv < 575)
        dm = np.where(o["final"], o["davg"], 0.0)[np.round(vv[inb]).astype(int), np.round(uu[inb]).astype(int)]; z = Xc[inb, 2]
        good = dm > 0; errs.append(np.abs(z[good] - dm[good]) / dm[good])
        out.setdefault(name, {})[f"view{kk}_rays_hit"] = int(ok.sum())
    e = np.concatenate(errs); out[name].update(n=int(len(e)), rel_err_p50=float(np.median(e)) if len(e) else None, frac_lt_1pct=float((e < 0.01).mean()) if len(e) else None)
    print(name, out[name], flush=True)
json.dump(out, open("l2control.json", "w"), indent=1)
