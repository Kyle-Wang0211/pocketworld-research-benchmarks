"""Algorithmic floater/hole fix (NOT parameter tuning): TSDF volumetric fusion of
the cached per-frame depth maps. Free-space carving geometrically removes floating
points (rays from other cameras pass through the empty space a floater sits in) and
fills small holes — what point-level gates structurally cannot do.

Reuses the v8 pass-1 depth cache (no re-inference). Output: a mesh + sampled points,
aligned to the regular-COLMAP frame for the overlay page.

Usage: pw_diffmvs_tsdf.py MODEL_TXT_DIR CACHE_TAG OUT_TAG [VOXEL] [SDF_TRUNC] [CONF]
"""
from __future__ import annotations
import sys, os
from pathlib import Path
import numpy as np
import open3d as o3d
import pw_diffmvs_run as R

MODEL = Path(sys.argv[1]); CACHE_TAG = sys.argv[2]; TAG = sys.argv[3]
VOXEL = float(sys.argv[4]) if len(sys.argv) > 4 else 0.01
SDF_TRUNC = float(sys.argv[5]) if len(sys.argv) > 5 else 0.04
CONF = float(sys.argv[6]) if len(sys.argv) > 6 else 0.1   # mild garbage cut only; TSDF carves the rest
OUT = R.OUT
SFM_CMP = Path(__file__).resolve().parent / "sfm_cmp"


def quat_to_R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0); S, D = src-ms, dst-md
    U, d, Vt = np.linalg.svd(D.T@S/len(src)); Rr = U@Vt
    if np.linalg.det(Rr) < 0:
        U[:, -1] *= -1; Rr = U@Vt
    s = np.trace(np.diag(d))/((S**2).sum()/len(src))
    return s, Rr, md-s*Rr@ms


def parse_w2c(images_txt):
    w2c, cen = {}, {}
    L = [l for l in open(images_txt) if not l.startswith("#") and l.strip()]
    for i in range(0, len(L), 2):
        p = L[i].split()
        if len(p) < 10:
            continue
        Rm = quat_to_R(list(map(float, p[1:5]))); t = np.array(list(map(float, p[5:8])))
        W = np.eye(4); W[:3, :3] = Rm; W[:3, 3] = t
        w2c[p[9]] = W; cen[p[9]] = -Rm.T @ t
    return w2c, cen


def build_kmap():
    _, wdef, _ = R._load_meta(); Kmap = {}
    for win, wd in wdef.items():
        z = np.load(R.EXPAC / "windows" / f"win_{win:02d}.npz")
        for j, mi in enumerate(wd["frame_idx"]):
            Kmap.setdefault(mi, R.scaled_K(z["K"][j]))
    return Kmap


def main():
    man, _, _ = R._load_meta()
    name2mi = {Path(f["jpegPath"]).name: i for i, f in enumerate(man)}
    Kmap = build_kmap()
    w2c_s, cen_s = parse_w2c(MODEL / "images.txt")

    z = np.load(OUT / f"p1cache_sfm_{CACHE_TAG}.npz", allow_pickle=True)
    fr = z["frames"].tolist(); zd = z["depth"]; zc = z["conf"]; zr = z["drange"]
    depth = {n: zd[i].astype(np.float32) for i, n in enumerate(fr)}
    conf = {n: zc[i].astype(np.float32) for i, n in enumerate(fr)}
    drng = {n: tuple(zr[i]) for i, n in enumerate(fr)}
    names = [n for n in fr if n in w2c_s and name2mi.get(n) in Kmap]
    print(f"TSDF: {len(names)} frames, voxel={VOXEL} trunc={SDF_TRUNC} conf={CONF}", flush=True)

    vol = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=VOXEL, sdf_trunc=SDF_TRUNC,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
    for i, n in enumerate(names):
        K = Kmap[name2mi[n]]; d = depth[n].copy()
        dmin, dmax = drng[n]
        d[(conf[n] < CONF) | (d < dmin * 0.5) | (d > dmax)] = 0.0   # drop only garbage; TSDF carves floaters
        H, W = d.shape
        col = (R.load_image(name2mi[n]) * 255).astype(np.uint8)
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(np.ascontiguousarray(col)),
            o3d.geometry.Image(np.ascontiguousarray(d)),
            depth_scale=1.0, depth_trunc=dmax * 1.2, convert_rgb_to_intensity=False)
        intr = o3d.camera.PinholeCameraIntrinsic(W, H, K[0, 0], K[1, 1], K[0, 2], K[1, 2])
        vol.integrate(rgbd, intr, w2c_s[n])     # extrinsic = world->camera
        if i % 50 == 0:
            print(f"  integrate {i}/{len(names)}", flush=True)

    mesh = vol.extract_triangle_mesh(); mesh.compute_vertex_normals()
    print(f"raw mesh: {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris", flush=True)
    # keep the largest connected component (drops detached floater shells)
    mesh.remove_degenerate_triangles(); mesh.remove_unreferenced_vertices()

    # align SfM-frame mesh -> regular COLMAP frame (same as the point pipeline)
    colmap_c = parse_w2c(SFM_CMP / "txt_colmap/images.txt")[1]
    common = [n for n in names if n in colmap_c]
    s, Rm, t = umeyama(np.array([cen_s[n] for n in common]), np.array([colmap_c[n] for n in common]))
    print(f"align->COLMAP: common={len(common)} scale={s:.3f}", flush=True)
    V = np.asarray(mesh.vertices); mesh.vertices = o3d.utility.Vector3dVector((s*(Rm@V.T).T+t))
    mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(str(OUT / f"tsdf_{TAG}_mesh.ply"), mesh)
    pts = mesh.sample_points_uniformly(number_of_points=3_000_000)
    o3d.io.write_point_cloud(str(OUT / f"tsdf_{TAG}_pts.ply"), pts)
    print(f"wrote tsdf_{TAG}_mesh.ply ({len(mesh.triangles):,} tris) + tsdf_{TAG}_pts.ply", flush=True)


if __name__ == "__main__":
    main()
