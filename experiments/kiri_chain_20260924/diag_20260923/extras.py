"""(1) frame control for layer2F on CD meshes: depth at the RAY's own pixel;  (2) synthetic positive control for hole class C
(far-layer views overwrite the near-layer zero crossing, Open3D semantics);  (3) white-wall signed depth error of fused pixels;
(4) per-view before/after filter fractions per region."""
import numpy as np, open3d as o3d, open3d.core as o3c, json, csv
from replay_lib import *
out = {}
# ---------- (1)
d = json.load(open("/root/av_ep0_off/scene_dense.sfm")); I = d["intrinsics"][0]; W0 = int(I["width"]); H0 = int(I["height"])
f = float(I["focalLength"]) / float(I["sensorWidth"]) * W0; pp = [float(x) for x in I["principalPoint"]]
poses = {p["poseId"]: p["pose"]["transform"] for p in d["poses"]}; views = sorted([v for v in d["views"] if v["poseId"] in poses], key=lambda v: v["path"])
SW, SH = 336, 250; sca = W0 / SW; fx = f / sca; cx = (W0 / 2 + pp[0]) / sca; cy = (H0 / 2 + pp[1]) / sca
S = json.load(open("sim3_cd2av.json")); s = S["s"]; R = np.array(S["R"]); t = np.array(S["t"])
cm = o3d.io.read_triangle_mesh("coarse12_thr0.ply"); V = np.asarray(cm.vertices)
meshes = {"transformed": o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector((s * (R @ V.T)).T + t), cm.triangles), "untransformed(neg)": cm}
for name, me in meshes.items():
    scn = o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(me)); errs = []
    for kk in [0, 33, 66, 99]:
        tr = poses[views[kk]["poseId"]]; Rv = np.array([float(x) for x in tr["rotation"]]).reshape(3, 3, order="F"); C = np.array([float(x) for x in tr["center"]])
        u, v = np.meshgrid(np.arange(SW, dtype=np.float32), np.arange(SH, dtype=np.float32))
        dc = np.stack([(u - cx) / fx, (v - cy) / fx, np.ones_like(u)], -1).reshape(-1, 3); dw = dc @ Rv; dw /= np.linalg.norm(dw, axis=1, keepdims=True)
        th = scn.cast_rays(o3d.core.Tensor(np.concatenate([np.tile(C, (len(dw), 1)), dw], 1).astype(np.float32)))["t_hit"].numpy(); ok = np.isfinite(th)
        Pav = C + th[ok, None] * dw[ok]; Pcd = ((R.T @ (Pav - t).T) / s).T
        o = replay(kk, dict(PAIR_DATA)[kk]); K, E = o["K"].astype(np.float64), o["E"].astype(np.float64)
        dcd = (E[:3, :3] @ (R.T @ dw[ok].T)).T; up = (K @ dcd.T).T; ur = up[:, 0] / up[:, 2]; vr = up[:, 1] / up[:, 2]   # the ray's own pixel
        inb = (dcd[:, 2] > 0) & (ur >= 0) & (ur <= 767) & (vr >= 0) & (vr <= 575)
        dm = np.where(o["final"], o["davg"], 0.0)[np.round(vr[inb]).astype(int), np.round(ur[inb]).astype(int)]
        z = ((E[:3, :3] @ Pcd.T).T + E[:3, 3])[inb, 2]; g = dm > 0; errs.append(np.abs(z[g] - dm[g]) / dm[g])
    e = np.concatenate(errs); out.setdefault("frame_control", {})[name] = dict(n=int(len(e)), rel_err_p50=float(np.median(e)), frac_lt_2pct=float((e < 0.02).mean()))
print(out, flush=True)
# ---------- (2) synthetic: plane at Z0 seen by NNEAR views, plane at Z0+GAP seen by NFAR views
def synth(gap, nnear, nfar, vox=0.003, tr=0.04):
    vbg = o3d.t.geometry.VoxelBlockGrid(attr_names=("tsdf", "weight"), attr_dtypes=(o3c.float32, o3c.float32), attr_channels=((1), (1)),
        voxel_size=vox, block_resolution=16, block_count=20000, device=o3c.Device("CPU:0"))
    Kc = np.array([[200.0, 0, 100], [0, 200.0, 100], [0, 0, 1]]); Z0 = 1.0
    for i in range(nnear + nfar):
        E = np.eye(4); E[0, 3] = 0.01 * i
        z = Z0 + (gap if i >= nnear else 0.0); d16 = np.full((200, 200), int(round(z * 5000)), np.uint16)
        dimg = o3d.t.geometry.Image(o3c.Tensor(d16)); Kt = o3c.Tensor(Kc); Et = o3c.Tensor(E)
        c = vbg.compute_unique_block_coordinates(dimg, Kt, Et, 5000.0, 30.0, tr / vox); vbg.integrate(c, dimg, Kt, Et, 5000.0, 30.0, tr / vox)
    m = vbg.extract_triangle_mesh(weight_threshold=1.0).to_legacy(); Vm = np.asarray(m.vertices)
    near = int((np.abs(Vm[:, 2] - Z0) < 0.01).sum()) if len(Vm) else 0; far = int((np.abs(Vm[:, 2] - Z0 - gap) < 0.01).sum()) if len(Vm) and gap > 0.02 else None
    # column classification at the scene centre, same rule as classify.py (ray-level, +-trunc around Z0)
    hm = vbg.hashmap(); ai = hm.active_buf_indices().numpy(); keys = hm.key_tensor().numpy()[ai]
    T = vbg.attribute("tsdf").numpy().reshape(-1, 16, 16, 16)[ai]; W = vbg.attribute("weight").numpy().reshape(-1, 16, 16, 16)[ai]
    kd = {tuple(k): i for i, k in enumerate(keys)}
    def look(Iv):
        bk = Iv // 16; lc = Iv - bk * 16; b = kd.get(tuple(bk), -1)
        return (T[b, lc[2], lc[1], lc[0]], W[b, lc[2], lc[1], lc[0]]) if b >= 0 else (0.0, 0)
    col = []
    for zz in np.arange(Z0 - tr, Z0 + tr, vox):
        tv, wv = look(np.array([int(0.0 / vox), int(0.0 / vox), int(round(zz / vox))])); col.append((tv, wv))
    col = np.array(col); cross = np.any(np.diff(np.sign(col[:, 0])) != 0); cls = "C(no crossing, all w>=2)" if (not cross and col[:, 1].min() >= 2) else ("crossing" if cross else "other")
    return dict(near_layer_vertices=near, far_layer_vertices=far, centre_column_tsdf_min_max=[float(col[:, 0].min()), float(col[:, 0].max())], centre_column_class=cls)
out["synthetic"] = {"far layer 0.15 beyond trunc, 2 near + 3 far": synth(0.15, 2, 3), "far layer 0.15, 3 near + 2 far": synth(0.15, 3, 2),
                    "far layer 0.02 (< trunc), 2 near + 3 far": synth(0.02, 2, 3), "no far layer, 5 near (control)": synth(0.0, 5, 0)}
print(json.dumps(out["synthetic"], indent=1), flush=True)
# ---------- (3) white-wall fused depth signed error vs plane (CD units), and (4) before-filter validity
Rr = json.load(open("regions_planes.json")); L = np.load("labels4.npz")["labels"]
uu, vv = np.meshgrid(np.arange(768) + 0.0, np.arange(576) + 0.0); errs = {1: [], 4: [], 2: []}; valid = {c: [0, 0] for c in (1, 2, 3, 4)}
for rv, sv in PAIR_DATA:
    o = replay(rv, sv); K, E = o["K"].astype(np.float64), o["E"].astype(np.float64); Rw = E[:3, :3]; C = -Rw.T @ E[:3, 3]
    rw = (Rw.T @ (np.linalg.inv(K) @ np.stack([uu.ravel(), vv.ravel(), np.ones(uu.size)]))).T
    rng = ((o["d"] > o["dmin"]) & (o["d"] < o["dmax"])).ravel()
    for c in valid: m = (L[rv] == c).ravel(); valid[c][0] += int(m.sum()); valid[c][1] += int((m & rng).sum())
    for c, key in ((1, "wall"), (4, "white"), (2, "floor")):
        n = np.array(Rr[key]["n"]); dd = Rr[key]["d"]; m = ((L[rv] == c) & o["final"]).ravel()
        if m.sum() == 0: continue
        z = -(n @ C + dd) / (rw[m] @ n); errs[c].append(o["davg"].ravel()[m] - z)
for c, name in ((1, "fabric_wall"), (4, "white_wall"), (2, "floor")):
    e = np.concatenate(errs[c]); out[f"{name}_fused_depth_minus_plane_CD"] = dict(n=int(len(e)), p5_p50_p95=np.percentile(e, [5, 50, 95]).round(4).tolist(),
        frac_behind_gt_trunc=float((e > 0.04).mean()), frac_front_gt_trunc=float((e < -0.04).mean()), frac_within_trunc=float((np.abs(e) <= 0.04).mean()))
out["before_filter_depth_in_range_frac"] = {n: valid[c][1] / max(valid[c][0], 1) for c, n in ((1, "fabric_wall"), (2, "floor"), (3, "suitcase"), (4, "white_wall"))}
rows = list(csv.DictReader(open("filt_per_view_4.csv")))
for reg in ("wall", "white", "floor", "suitcase"):
    fr = np.array([int(r["final"]) / int(r["N"]) for r in rows if r["region"] == reg and int(r["N"]) >= 5000])
    out.setdefault("per_view_final_frac", {})[reg] = dict(views=int(len(fr)), min=float(fr.min()), p10=float(np.percentile(fr, 10)), p50=float(np.median(fr)), p90=float(np.percentile(fr, 90)), max=float(fr.max()))
print(json.dumps({k: v for k, v in out.items() if k != "synthetic"}, indent=1))
json.dump(out, open("extras.json", "w"), indent=1)
