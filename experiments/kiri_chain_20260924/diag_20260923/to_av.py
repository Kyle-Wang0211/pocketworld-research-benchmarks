"""CD (CasDiffMVS cams) frame -> AliceVision SfM frame used by /root/tsdf/layer2F.py, via Umeyama Sim3 on the 132 camera centres
(same method as /root/align_C.py). Control: first-hit depth of layer2F-style rays vs the CD depth maps, transformed vs untransformed."""
import numpy as np, open3d as o3d, json, sys
from replay_lib import *
IN, OUT = sys.argv[1], sys.argv[2]
d = json.load(open("/root/av_ep0_off/scene_dense.sfm")); poses = {p["poseId"]: p["pose"]["transform"] for p in d["poses"]}
views = sorted([v for v in d["views"] if v["poseId"] in poses], key=lambda v: v["path"])
A = []; B = []
for k in range(132):
    t = poses[views[k]["poseId"]]; B.append([float(x) for x in t["center"]]); K, E, _, _ = cam(k); A.append(-E[:3, :3].T @ E[:3, 3])
A = np.array(A, np.float64); B = np.array(B)
mA, mB = A.mean(0), B.mean(0); Xa, Xb = A - mA, B - mB; U, S, Vt = np.linalg.svd(Xb.T @ Xa / len(A)); D = np.eye(3); D[2, 2] = np.sign(np.linalg.det(U @ Vt))
R = U @ D @ Vt; s = np.trace(np.diag(S) @ D) / Xa.var(0).sum(); t = mB - s * R @ mA
res = np.linalg.norm((s * (R @ A.T)).T + t - B, axis=1); print(f"Sim3 CD->AV scale {s:.6f} centre residual (AV units) p50 {np.median(res):.4f} max {res.max():.4f}", flush=True)
m = o3d.io.read_triangle_mesh(IN); V = np.asarray(m.vertices)
m2 = o3d.geometry.TriangleMesh(o3d.utility.Vector3dVector((s * (R @ V.T)).T + t), m.triangles); del m
o3d.io.write_triangle_mesh(OUT, m2); print("wrote", OUT, len(V), flush=True)
json.dump(dict(s=s, R=R.tolist(), t=t.tolist(), centre_resid_p50=float(np.median(res)), centre_resid_max=float(res.max())), open("sim3_cd2av.json", "w"), indent=1)
