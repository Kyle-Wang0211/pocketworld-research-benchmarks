"""Positive control for hole class C: same synthetic scene, but every view integrates into the UNION of all views' blocks
(i.e. without Open3D's per-view block restriction). If far views could write +1 into near-layer voxels, class C appears here."""
import numpy as np, open3d as o3d, open3d.core as o3c, json
def synth(gap, nnear, nfar, union, vox=0.003, tr=0.04):
    vbg = o3d.t.geometry.VoxelBlockGrid(attr_names=("tsdf", "weight"), attr_dtypes=(o3c.float32, o3c.float32), attr_channels=((1), (1)),
        voxel_size=vox, block_resolution=16, block_count=20000, device=o3c.Device("CPU:0"))
    Kc = o3c.Tensor(np.array([[200.0, 0, 100], [0, 200.0, 100], [0, 0, 1]])); Z0 = 1.0; imgs = []
    for i in range(nnear + nfar):
        E = np.eye(4); E[0, 3] = 0.01 * i; z = Z0 + (gap if i >= nnear else 0.0)
        imgs.append((o3d.t.geometry.Image(o3c.Tensor(np.full((200, 200), int(round(z * 5000)), np.uint16))), o3c.Tensor(E)))
    coords = [vbg.compute_unique_block_coordinates(d, Kc, E, 5000.0, 30.0, tr / vox) for d, E in imgs]
    allc = o3c.Tensor(np.unique(np.concatenate([c.numpy() for c in coords]), axis=0))
    for (d, E), c in zip(imgs, coords): vbg.integrate(allc if union else c, d, Kc, E, 5000.0, 30.0, tr / vox)
    Vm = np.asarray(vbg.extract_triangle_mesh(weight_threshold=1.0).to_legacy().vertices)
    return dict(near_layer_vertices=int((np.abs(Vm[:, 2] - Z0) < 0.01).sum()) if len(Vm) else 0,
                far_layer_vertices=int((np.abs(Vm[:, 2] - Z0 - gap) < 0.01).sum()) if len(Vm) else 0)
res = {}
for gap in (0.06, 0.1, 0.15, 0.3):
    res[f"gap {gap} CD, 2 near + 3 far, per-view blocks (production)"] = synth(gap, 2, 3, False)
    res[f"gap {gap} CD, 2 near + 3 far, union blocks (pos. control)"] = synth(gap, 2, 3, True)
res["no far layer, 5 near (control)"] = synth(0.0, 5, 0, False)
print(json.dumps(res, indent=1)); json.dump(res, open("synth2.json", "w"), indent=1)
