"""Offscreen render of a mesh/point cloud from a few fixed world viewpoints, so
DiffMVS output and the DA3 baseline can be compared at matched camera poses.
Usage: pw_render.py <ply> <out_prefix> [point]
"""
import sys
from pathlib import Path
import numpy as np
import open3d as o3d
import open3d.visualization.rendering as rendering

ply = Path(sys.argv[1]); prefix = sys.argv[2]
as_point = len(sys.argv) > 3 and sys.argv[3] == "point"
W = H = 900

if as_point:
    geo = o3d.io.read_point_cloud(str(ply))
else:
    geo = o3d.io.read_triangle_mesh(str(ply)); geo.compute_vertex_normals()

aabb = geo.get_axis_aligned_bounding_box()
center = aabb.get_center(); ext = aabb.get_extent()
rad = float(np.linalg.norm(ext)) * 0.5
print(f"{ply.name}: center={center.round(2)} extent={ext.round(2)}", flush=True)

rnd = rendering.OffscreenRenderer(W, H)
rnd.scene.set_background([0.1, 0.1, 0.1, 1.0])
mat = rendering.MaterialRecord()
mat.shader = "defaultUnlit" if as_point else "defaultLit"
mat.point_size = 2.0
rnd.scene.add_geometry("g", geo, mat)
rnd.scene.scene.set_sun_light([0.3, -0.6, -0.7], [1, 1, 1], 75000)
rnd.scene.scene.enable_sun_light(True)

# ARKit world: Y up. Look at the scene center from several azimuths, slightly above.
up = [0, 1, 0]
views = {
    "top": (center + np.array([0.2, rad * 1.6, 0.2]), [0, 0, -1]),
    "persp": (center + np.array([rad * 1.1, rad * 1.0, rad * 1.1]), up),
    "front": (center + np.array([0.1, rad * 0.5, rad * 1.7]), up),
    "low": (center + np.array([rad * 1.3, rad * 0.25, rad * 0.6]), up),
}
for name, (eye, upv) in views.items():
    rnd.scene.camera.look_at(center.tolist(), eye.tolist(), upv)
    img = rnd.render_to_image()
    op = ply.parent / f"{prefix}_{name}.png"
    o3d.io.write_image(str(op), img)
    print("wrote", op.name, flush=True)
