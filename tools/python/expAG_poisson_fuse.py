#!/usr/bin/env python3
"""expAG: does ghosting survive Poisson surface fusion?

Raw point overlay STACKS every observation -> parallel co-oriented
depth-offset layers read as ghosting (user confirmed via normal
coloring: one color per plane = consistent normals, the precondition
for Poisson to collapse the layers). This runs screened Poisson
(Open3D / Kazhdan, same family as our shipped SAP/DPSR; SAP >= this)
on the Fix-B clouds and renders the MESH so we judge ghosting on the
deliverable surface, not the raw points.

Normals are baked into the PLY color as (n+1)/2; we decode them back
(reusing the already-eyeball-validated normals) instead of re-orienting.
"""
import sys
import numpy as np
import open3d as o3d
from pathlib import Path

DESK = Path.home() / "Desktop/expF2_easy_clouds_2026_06_12"
OUT = DESK / "poisson"
OUT.mkdir(exist_ok=True)

ALL_JOBS = {"normals_old11.ply": "old11", "normals_new12.ply": "new12",
            "union_preview.ply": "union"}
POISSON_DEPTH = 9           # octree depth; 11 crashes PoissonRecon C++ on this data
DENSITY_TRIM_Q = 0.04       # drop lowest-density (extrapolated) verts
VOXEL = 0.004               # 4mm pre-downsample to tame point count
# single-file mode: argv[1] = ply filename (so a C++ abort in one job
# doesn't kill the others — they run in separate processes)
JOBS = ([(sys.argv[1], ALL_JOBS.get(sys.argv[1], "out"))]
        if len(sys.argv) > 1 else list(ALL_JOBS.items()))


def load_decode(path):
    pcd = o3d.io.read_point_cloud(str(path))
    cols = np.asarray(pcd.colors)            # [0,1]
    normals = cols * 2.0 - 1.0               # decode (n+1)/2 -> n
    nrm = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.clip(nrm, 1e-6, None)
    pcd.normals = o3d.utility.Vector3dVector(normals)
    return pcd


def sanity_floor(pcd):
    # floor points (lowest Y band) should have normal ~ +/-Y if decode is right
    pts = np.asarray(pcd.points)
    nrm = np.asarray(pcd.normals)
    ylo = pts[:, 1] < np.percentile(pts[:, 1], 10)
    if ylo.sum() == 0:
        return None
    return float(np.median(np.abs(nrm[ylo, 1])))


for fname, tag in JOBS:
    p = DESK / fname
    if not p.exists():
        print(f"skip {fname} (missing)", flush=True)
        continue
    pcd = load_decode(p)
    n0 = len(pcd.points)
    floor_ny = sanity_floor(pcd)
    print(f"[{tag}] {n0:,} pts, floor |n_y| median {floor_ny}", flush=True)

    pcd = pcd.voxel_down_sample(VOXEL)
    print(f"[{tag}] after {VOXEL*1000:.0f}mm voxel: {len(pcd.points):,} pts", flush=True)

    mesh, dens = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=POISSON_DEPTH, linear_fit=True, n_threads=1)
    print(f"[{tag}] poisson ok at depth {POISSON_DEPTH} (serial)", flush=True)
    dens = np.asarray(dens)
    keep = dens > np.quantile(dens, DENSITY_TRIM_Q)
    mesh.remove_vertices_by_mask(~keep)
    mesh.compute_vertex_normals()
    print(f"[{tag}] poisson mesh: {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris", flush=True)
    o3d.io.write_triangle_mesh(str(OUT / f"mesh_{tag}.ply"), mesh)

    # offscreen render from 3 angles
    try:
        bb = mesh.get_axis_aligned_bounding_box()
        ctr = bb.get_center()
        ext = np.linalg.norm(bb.get_extent())
        for ai, (ex, ey, ez) in enumerate([(0, -1.4, 0.9), (1.2, -0.8, 0.6), (0, -0.2, 1.6)]):
            vis = o3d.visualization.Visualizer()
            vis.create_window(visible=False, width=1400, height=1000)
            vis.add_geometry(mesh)
            opt = vis.get_render_option()
            opt.mesh_show_back_face = True
            opt.light_on = True
            vc = vis.get_view_control()
            cam = vc.convert_to_pinhole_camera_parameters()
            eye = ctr + np.array([ex, ey, ez]) * ext
            front = ctr - eye
            front = front / np.linalg.norm(front)
            vc.set_lookat(ctr)
            vc.set_front(front)
            vc.set_up([0, 0, 1])
            vc.set_zoom(0.7)
            vis.poll_events(); vis.update_renderer()
            vis.capture_screen_image(str(OUT / f"render_{tag}_a{ai}.png"), do_render=True)
            vis.destroy_window()
        print(f"[{tag}] rendered 3 views", flush=True)
    except Exception as e:
        print(f"[{tag}] render failed ({e}); mesh PLY still written", flush=True)

print("EXPAG-DONE", flush=True)
