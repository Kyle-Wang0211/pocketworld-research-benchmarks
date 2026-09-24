"""Where are the production mesh boundary edges (hole rims)? Save midpoints; density grid; project densest cells into views."""
import numpy as np, open3d as o3d, json, sys, cv2
sys.path.insert(0, "/root/diffmvs")
from datasets.data_io import read_camera_parameters
MESH = sys.argv[1]; OUT = sys.argv[2]
m = o3d.io.read_triangle_mesh(MESH); V = np.asarray(m.vertices); T = np.asarray(m.triangles).astype(np.int64); N = np.int64(len(V))
e = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]); e.sort(1); key = e[:, 0] * N + e[:, 1]; del e
key.sort(); first = np.r_[True, key[1:] != key[:-1]]; idx = np.flatnonzero(first); cnt = np.diff(np.r_[idx, len(key)])
bkey = key[idx[cnt == 1]]; del key, first, idx, cnt
ba = bkey // N; bb = bkey % N; mid = (0.5 * (V[ba] + V[bb])).astype(np.float32)
# boundary loops: walk the boundary graph (each boundary vertex has degree 2 in a manifold boundary)
import scipy.sparse as sp, scipy.sparse.csgraph as cg
u, inv = np.unique(np.concatenate([ba, bb]), return_inverse=True); n = len(u); ia = inv[:len(ba)]; ib = inv[len(ba):]
G = sp.coo_matrix((np.ones(len(ia)), (ia, ib)), shape=(n, n)); ncomp, lab = cg.connected_components(G, directed=False)
elab = lab[ia]; loop_len = np.bincount(elab, minlength=ncomp)
np.savez_compressed(OUT + ".npz", mid=mid, loop_len_of_edge=loop_len[elab].astype(np.int32), elab=elab.astype(np.int32))
print("boundary edges", len(bkey), "loops", ncomp, "loop length p50/p90/p99", np.percentile(loop_len, [50, 90, 99]), "loops<=12 edges", int((loop_len <= 12).sum()), flush=True)
# centroid of each loop
cx = np.zeros((ncomp, 3)); np.add.at(cx, elab, mid); cx /= loop_len[:, None]
small = loop_len <= 12
C = cx[small]; g = np.floor(C / 0.1).astype(np.int64); gu, gc = np.unique(g, axis=0, return_counts=True)
o = np.argsort(-gc)[:15]; print("densest 0.1CD cells of small loops (count, center):"); [print(" ", int(gc[i]), ((gu[i] + 0.5) * 0.1).round(2).tolist()) for i in o]
np.save(OUT + "_smallloop_centroids.npy", C.astype(np.float32))
# project small-loop centroids into selected views (dots), for visual location
ids = [0, 40, 74, 90, 104, 110, 123, 124, 131, 20, 60, 115]; ims = []
for k in ids:
    K, E, _, _ = read_camera_parameters(f"/root/arm_full_ep0_tsdf/cams/{k:08d}_cam.txt"); im = cv2.imread(f"/root/arm_full_ep0_tsdf/images/{k:08d}.jpg")
    X = (E[:3, :3] @ C.T).T + E[:3, 3]; ok = X[:, 2] > 0; uv = (K @ X[ok].T).T; uv = uv[:, :2] / uv[:, 2:3]
    inb = (uv[:, 0] >= 0) & (uv[:, 0] < 768) & (uv[:, 1] >= 0) & (uv[:, 1] < 576); hm = np.zeros((576, 768), np.float32)
    np.add.at(hm, (uv[inb, 1].astype(int), uv[inb, 0].astype(int)), 1); hm = cv2.GaussianBlur(hm, (0, 0), 3)
    hm = np.clip(hm / (np.percentile(hm[hm > 0], 99) + 1e-9), 0, 1); col = cv2.applyColorMap((hm * 255).astype(np.uint8), cv2.COLORMAP_HOT)
    mix = np.where(hm[..., None] > 0.05, cv2.addWeighted(im, 0.4, col, 0.6, 0), im)
    mix = cv2.resize(mix, (384, 288)); cv2.putText(mix, str(k), (6, 28), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2); ims.append(mix)
cv2.imwrite(OUT + "_views.jpg", np.vstack([np.hstack(ims[i:i + 4]) for i in range(0, 12, 4)]))
