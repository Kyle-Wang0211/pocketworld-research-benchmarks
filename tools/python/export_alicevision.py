"""Export CasDiffMVS cached depth + SfM(COLMAP) poses -> AliceVision sfmData(JSON)
+ per-view ray-distance depth EXRs, so aliceVision_meshing (fuseCut Delaunay graph-cut)
can mesh with visibility carving.

Corrections vs the generic recipe (our data, verified):
- poses are COLMAP/GLOMAP w2c (OpenCV +Z fwd/+Y down) -> NO ARKit diag(1,-1,-1) flip.
- K = ARKit Kmap @512x896 (the K depth was inferred with), NOT cameras.txt(4224x2376).
- depth is planar-Z -> convert to EUCLIDEAN RAY distance (silent killer #1).
- EXR filename = integer viewId (silent killer #3).

usage: export_alicevision.py OUTDIR [conf=0.1] [smooth=0]
"""
import sys, os, json, numpy as np, cv2
from pathlib import Path
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import pw_diffmvs_run as R

OUTDIR = Path(sys.argv[1]); CONF = float(sys.argv[2]) if len(sys.argv) > 2 else 0.1
SMOOTH = int(sys.argv[3]) if len(sys.argv) > 3 else 0
HERE = Path(__file__).resolve().parent
MODEL = HERE / "sfm_cmp/sfm_v8/txt_glomap"
CACHE = R.OUT / "p1cache_sfm_v8full.npz"
DEPTHDIR = OUTDIR / "depthMaps"; DEPTHDIR.mkdir(parents=True, exist_ok=True)


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
        w2c[p[9]] = (quat_to_R(list(map(float, p[1:5]))), np.array(list(map(float, p[5:8]))))
    return w2c


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
jpath = {Path(f["jpegPath"]).name: f["jpegPath"] for f in man}
Kmap = build_kmap(); Kmed = np.median(np.stack(list(Kmap.values())), 0)
w2c_s = parse_w2c(MODEL)
names = [n for n in frames if n in w2c_s and n in name2mi]
H, W = 512, 896

# precompute ray-length factor per pixel: ||K^-1 [u,v,1]|| (depends on K -> per-view)
views, intrinsics, poses = [], [], []
for idx, n in enumerate(names):
    vid = 1000 + idx                                   # integer viewId (nonzero)
    K = Kmap.get(name2mi[n], Kmed)
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    rayfac = np.sqrt(((uu - cx) / fx)**2 + ((vv - cy) / fy)**2 + 1.0).astype(np.float32)
    d = depth[n].copy()
    if SMOOTH:
        d = cv2.bilateralFilter(d, 5, 0.1, 5)
    d[conf[n] < CONF] = 0.0
    ray = (d * rayfac).astype(np.float32)              # planar-Z -> euclidean ray distance
    ray[d <= 0] = 0.0
    cv2.imwrite(str(DEPTHDIR / f"{vid}_depthMap.exr"), ray)
    Rw2c, t = w2c_s[n]; C = (-Rw2c.T @ t)
    views.append({"viewId": str(vid), "poseId": str(vid), "frameId": str(vid),
                  "intrinsicId": str(vid), "resectionId": "4294967295",
                  "path": jpath[n], "width": str(W), "height": str(H), "metadata": {}})
    intrinsics.append({"intrinsicId": str(vid), "width": str(W), "height": str(H),
                       "sensorWidth": str(float(W)), "sensorHeight": str(float(H)),
                       "serialNumber": "pocketworld", "type": "pinhole",
                       "initializationMode": "CALIBRATED",
                       "focalLength": str(float(fx)), "pixelRatio": str(float(fy/fx)),
                       "principalPoint": [str(float(cx)), str(float(cy))],
                       "distortionType": "none", "undistortionType": "none",
                       "distortionParams": [], "undistortionParams": [],
                       "undistortionOffset": ["0.0", "0.0"], "locked": "false"})
    poses.append({"poseId": str(vid), "pose": {"transform": {
        "rotation": [str(float(v)) for v in Rw2c.reshape(-1)],
        "center": [str(float(v)) for v in C]}, "locked": "1"}})

sfm = {"version": ["1", "2", "9"], "views": views, "intrinsics": intrinsics, "poses": poses}
(OUTDIR / "scene.sfm").write_text(json.dumps(sfm, indent=1))
print(f"wrote {OUTDIR}/scene.sfm + {len(names)} EXR depthMaps (ray-distance, conf>{CONF}, smooth={SMOOTH})")
print(f"viewId range {1000}-{1000+len(names)-1}; depth e.g. {DEPTHDIR}/1000_depthMap.exr")
