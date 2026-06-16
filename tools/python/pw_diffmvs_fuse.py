"""Fuse DiffMVS per-frame depths into a world point cloud, test floor geometry
(single-layer? flat?), and build a screened-Poisson mesh to compare vs the DA3
baseline. Answers brief criteria 2 (multi-view consistency, no BA), 3 (thin
structures), 4 (textureless handled), 6 (vs colored_mesh_fixb93_poi.ply).

Normals are oriented toward the camera centroid (fast) instead of
orient_normals_consistent_tangent_plane (MST -> minutes on big clouds).
Raw fused cloud is cached to npz so meshing can be re-tuned without re-inferring.
"""
from __future__ import annotations
import sys, time
from pathlib import Path
import numpy as np
import open3d as o3d
import pw_diffmvs_common as C
import pw_diffmvs_run as R

CONF_THR = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
METHOD = sys.argv[2] if len(sys.argv) > 2 else "diffmvs"
VOXEL = 0.006
N_WIN = 33
OUT = R.OUT
CACHE = OUT / f"rawfused_{METHOD}.npz"


def build_raw():
    dev = C.pick_device("cpu")
    model, _ = C.build_model(METHOD, dev)
    pts, cols, confs, camc = [], [], [], []
    t0 = time.time()
    for win in range(N_WIN):
        for ref in (0, 9):
            try:
                res = R.run_one(win, ref, 5, "cpu", METHOD, model=model, dev=dev)
            except Exception as e:
                print(f"  win{win} ref{ref} skip: {str(e)[:80]}", flush=True); continue
            z = np.load(res["od"] / "points.npz")
            pts.append(z["xyz"]); cols.append(z["rgb"]); confs.append(z["conf"])
            w2c = res["w2c"]; camc.append(-w2c[:3, :3].T @ w2c[:3, 3])
    P = np.concatenate(pts); Cc = np.concatenate(cols); Cf = np.concatenate(confs)
    cam_centroid = np.mean(camc, axis=0)
    np.savez_compressed(CACHE, xyz=P, rgb=Cc, conf=Cf, cam_centroid=cam_centroid)
    print(f"\nfused raw points={len(P):,}  elapsed={time.time()-t0:.1f}s  cam_centroid={cam_centroid.round(2)}",
          flush=True)
    return P, Cc, Cf, cam_centroid


def main():
    if CACHE.exists():
        d = np.load(CACHE); P, Cc, Cf, cc = d["xyz"], d["rgb"], d["conf"], d["cam_centroid"]
        print(f"loaded cache {CACHE.name}: {len(P):,} pts", flush=True)
    else:
        P, Cc, Cf, cc = build_raw()

    keep = (Cf >= CONF_THR) & np.isfinite(P).all(1)
    P, Cc = P[keep], Cc[keep]
    print(f"after conf>={CONF_THR}: {len(P):,}", flush=True)

    pc = o3d.geometry.PointCloud()
    pc.points = o3d.utility.Vector3dVector(P.astype(np.float64))
    pc.colors = o3d.utility.Vector3dVector(Cc.astype(np.float64) / 255.0)
    pc = pc.voxel_down_sample(VOXEL)
    print(f"after voxel {VOXEL*1000:.0f}mm: {len(pc.points):,}", flush=True)

    # floor geometry: largest planar structure
    m, inl = pc.segment_plane(distance_threshold=0.01, ransac_n=3, num_iterations=2000)
    a, b, c, dd = m; n = np.array([a, b, c]); n /= np.linalg.norm(n)
    xyz = np.asarray(pc.points); dist = np.abs(xyz @ n + dd)
    rms_mm = float(np.sqrt(np.mean(dist[inl] ** 2))) * 1000
    print(f"floor plane normal={n.round(3)} inliers={len(inl):,}/{len(xyz):,} "
          f"thickness RMS={rms_mm:.1f}mm (DA3 baseline w/ BA ~18mm)", flush=True)

    # clean before meshing: Open3D Poisson segfaults ("Failed to close loop")
    # on noisy clouds with outliers / bad normals -> scrub aggressively.
    pc = pc.remove_non_finite_points()
    pc, _ = pc.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
    print(f"after outlier removal: {len(pc.points):,}", flush=True)
    o3d.io.write_point_cloud(str(OUT / f"fused_{METHOD}_conf{CONF_THR}.ply"), pc)

    pc.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=0.05, max_nn=30))
    pc.orient_normals_towards_camera_location(cc.astype(np.float64))
    for depth in (10, 9, 8):
        try:
            mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
                pc, depth=depth, scale=1.1, linear_fit=True)
            dens = np.asarray(dens)
            mesh.remove_vertices_by_mask(dens < np.quantile(dens, 0.05))
            mp = OUT / f"mesh_{METHOD}_conf{CONF_THR}.ply"
            o3d.io.write_triangle_mesh(str(mp), mesh)
            print(f"poisson(depth={depth}) verts={len(mesh.vertices):,} "
                  f"tris={len(mesh.triangles):,} -> {mp.name}", flush=True)
            break
        except Exception as e:
            print(f"poisson depth={depth} failed: {str(e)[:80]}", flush=True)


if __name__ == "__main__":
    main()
