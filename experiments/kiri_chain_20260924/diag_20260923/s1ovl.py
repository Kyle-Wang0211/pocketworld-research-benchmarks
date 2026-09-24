import numpy as np, open3d as o3d, json, cv2, sys
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_camera_parameters
R = json.load(open("regions_planes.json")); nw = np.array(R["wall"]["n"]); dw = R["wall"]["d"]; nf = np.array(R["floor"]["n"]); df = R["floor"]["d"]
pc = o3d.io.read_point_cloud("/root/arm_full_ep0_tsdf/pc_t3.ply").voxel_down_sample(0.005); P = np.asarray(pc.points)
sw = P @ nw + dw; h = P @ nf + df
groups = {"S1(+0.41 in front of fabric wall)": (np.abs(sw - 0.408) < 0.04), "ghost floor (-0.07)": (np.abs(h + 0.07) < 0.025)}
cm = o3d.io.read_triangle_mesh("coarse12_thr0.ply"); scn = o3d.t.geometry.RaycastingScene(); scn.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(cm))
for gname, sel in groups.items(): print(gname, int(sel.sum()), "points in pc_t3 (5mm-downsampled)")
ids = [0, 20, 40, 60, 90, 104, 110, 115, 124, 131, 74, 12]; ims = []
for k in ids:
    K, E, _, _ = read_camera_parameters(f"/root/arm_full_ep0_tsdf/cams/{k:08d}_cam.txt"); im = cv2.imread(f"/root/arm_full_ep0_tsdf/images/{k:08d}.jpg"); ov = im.copy()
    Cc = -E[:3, :3].T @ E[:3, 3]
    for (gname, sel), col in zip(groups.items(), [(255, 0, 255), (0, 255, 255)]):
        Q = P[sel]; X = (E[:3, :3] @ Q.T).T + E[:3, 3]; ok = X[:, 2] > 0; Q = Q[ok]; X = X[ok]
        uv = (K @ X.T).T; uv = uv[:, :2] / uv[:, 2:3]; inb = (uv[:, 0] >= 0) & (uv[:, 0] < 768) & (uv[:, 1] >= 0) & (uv[:, 1] < 576)
        Q = Q[inb]; uv = uv[inb]
        d = Q - Cc; dist = np.linalg.norm(d, axis=1); th = scn.cast_rays(o3d.core.Tensor(np.concatenate([np.tile(Cc, (len(Q), 1)), d / dist[:, None]], 1).astype(np.float32)))["t_hit"].numpy()
        vis = ~(th < dist - 0.05)
        ov[uv[vis, 1].astype(int), uv[vis, 0].astype(int)] = col
    m = cv2.addWeighted(im, 0.5, ov, 0.5, 0); m = cv2.resize(m, (384, 288)); cv2.putText(m, str(k), (6, 28), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2); ims.append(m)
cv2.imwrite("s1_ovl.jpg", np.vstack([np.hstack(ims[i:i + 4]) for i in range(0, 12, 4)]))
