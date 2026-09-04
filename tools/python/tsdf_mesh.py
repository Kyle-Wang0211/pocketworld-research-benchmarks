"""TSDF + Marching Cubes from the cached per-frame CasDiffMVS depth maps + SfM poses.
Multi-view depth averaging into a voxel grid -> flat floor (noise averaged out),
native open-scene support. Complementary to screened-Poisson (which eats the noisy
cloud directly). Output mesh aligned to the regular-COLMAP frame for comparison.

usage: tsdf_mesh.py out.ply [voxel=0.015] [conf=0.1]   (reuses p1cache_sfm_v8full.npz)
"""
import sys, os, numpy as np, open3d as o3d
from pathlib import Path
import pw_diffmvs_run as R

VOXEL = float(sys.argv[2]) if len(sys.argv) > 2 else 0.015
CONF = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1
TRUNC = VOXEL * 4
OUTP = sys.argv[1]
HERE = Path(__file__).resolve().parent
MODEL = HERE / "sfm_cmp/sfm_v8/txt_glomap"
COLMAP_IMAGES = HERE / "sfm_cmp/txt_colmap/images.txt"
CACHE = R.OUT / "p1cache_sfm_v8full.npz"


def quat_to_R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def parse_w2c(mdir):
    w2c = {}
    L = [l for l in open(mdir / "images.txt") if not l.startswith("#") and l.strip()]
    for i in range(0, len(L), 2):
        p = L[i].split()
        if len(p) < 10:
            continue
        W = np.eye(4); W[:3, :3] = quat_to_R(list(map(float, p[1:5]))); W[:3, 3] = list(map(float, p[5:8]))
        w2c[p[9]] = W
    return w2c


def centers(images_txt):
    out = {}
    L = [l for l in open(images_txt) if not l.startswith("#") and l.strip()]
    for i in range(0, len(L), 2):
        p = L[i].split()
        if len(p) < 10:
            continue
        out[p[9]] = -quat_to_R(list(map(float, p[1:5]))).T @ np.array(list(map(float, p[5:8])))
    return out


def umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0); S, D = src-ms, dst-md
    U, d, Vt = np.linalg.svd(D.T@S/len(src)); Rr = U@Vt
    if np.linalg.det(Rr) < 0:
        U[:, -1] *= -1; Rr = U@Vt
    s = np.trace(np.diag(d))/((S**2).sum()/len(src))
    return s, Rr, md - s*Rr@ms


def build_kmap():
    _, wdef, _ = R._load_meta(); km = {}
    for win, wd in wdef.items():
        z = np.load(R.EXPAC / "windows" / f"win_{win:02d}.npz")
        for j, mi in enumerate(wd["frame_idx"]):
            km.setdefault(mi, R.scaled_K(z["K"][j]))
    return km


z = np.load(CACHE, allow_pickle=True)
frames = list(z["frames"]); depth = {n: z["depth"][i].astype(np.float32) for i, n in enumerate(frames)}
conf = {n: z["conf"][i].astype(np.float32) for i, n in enumerate(frames)}
man, _, _ = R._load_meta()
name2mi = {Path(f["jpegPath"]).name: i for i, f in enumerate(man)}
Kmap = build_kmap(); Kmed = np.median(np.stack(list(Kmap.values())), 0)
w2c_s = parse_w2c(MODEL)
names = [n for n in frames if n in w2c_s and n in name2mi]
print(f"TSDF: {len(names)} frames, voxel={VOXEL}, conf>{CONF}", flush=True)

vol = o3d.pipelines.integration.ScalableTSDFVolume(
    voxel_length=VOXEL, sdf_trunc=TRUNC,
    color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8)
H, W = 512, 896
for k, n in enumerate(names):
    mi = name2mi[n]; K = Kmap.get(mi, Kmed)
    d = depth[n].copy(); d[conf[n] < CONF] = 0.0                      # drop low-conf pixels
    color = (R.load_image(mi) * 255).astype(np.uint8)
    o3dc = o3d.geometry.Image(np.ascontiguousarray(color))
    o3dd = o3d.geometry.Image(np.ascontiguousarray(d.astype(np.float32)))
    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        o3dc, o3dd, depth_scale=1.0, depth_trunc=30.0, convert_rgb_to_intensity=False)
    intr = o3d.camera.PinholeCameraIntrinsic(W, H, K[0, 0], K[1, 1], K[0, 2], K[1, 2])
    vol.integrate(rgbd, intr, w2c_s[n])                              # extrinsic = w2c
    if k % 80 == 0:
        print(f"  integrate {k}/{len(names)}", flush=True)
mesh = vol.extract_triangle_mesh(); mesh.compute_vertex_normals()
print(f"raw TSDF mesh: {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris", flush=True)

# align SfM-frame mesh -> regular-COLMAP frame (same umeyama as the point clouds)
cC = centers(COLMAP_IMAGES); cS = {n: -w2c_s[n][:3, :3].T @ w2c_s[n][:3, 3] for n in names}
common = [n for n in names if n in cC]
s, Rm, t = umeyama(np.array([cS[n] for n in common]), np.array([cC[n] for n in common]))
V = np.asarray(mesh.vertices); mesh.vertices = o3d.utility.Vector3dVector((s * (Rm @ V.T).T + t))
print(f"align->COLMAP: common={len(common)} scale={s:.3f}", flush=True)
o3d.io.write_triangle_mesh(OUTP, mesh)
print(f"wrote {OUTP}: {len(mesh.vertices):,} verts {len(mesh.triangles):,} tris", flush=True)
