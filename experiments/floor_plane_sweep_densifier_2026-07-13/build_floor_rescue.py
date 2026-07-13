#!/usr/bin/env python3
"""Prepare cap50 floor-rescue dataset.
Outputs into floor_rescue/:
  poses.json                 {frameId: {R,t,K,C,name,src,paths,...}}  world2cam CV convention
  production_floor.ply       SIFT-baseline floor points (band around ARKit-gravity floor plane)
  production_floor_stats.json
  floor_frame_ids.json       frames that see the floor (by reprojected-floor-point count)
  floor_frames_manifest.json floor frame id -> image paths
No torch / no cv2. Pure numpy+PIL+json. Data prep only (LoFTR runs downstream).
"""
import json, os, struct
import numpy as np

SP = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/b3b899a4-8125-4eb7-a21a-eb3d48c3d2a8/scratchpad"
OUT = SP + "/floor_rescue"
os.makedirs(OUT, exist_ok=True)

FED   = SP + "/cap50_diag/sfm_fed_frames.jsonl"
META  = SP + "/cap50_full_build/subset_meta_cap50full.json"
PLY   = SP + "/cap50_pull/sfm_sparse.ply"
GMASK = SP + "/cap50_diag/ghost_mask.json"
IMG_WORK = SP + "/cap50_full_build/images_full"          # 1024x576 png (matches K)
IMG_HI   = SP + "/cap50_frames/photos_highres"           # 3840x2160 jpg originals

FLIP = np.diag([1.0, -1.0, -1.0])   # ARKit cam axes (x right, y up, z back) -> CV (x right, y down, z fwd)

def load_fed():
    d = {}
    for ln in open(FED):
        ln = ln.strip()
        if not ln: continue
        j = json.loads(ln)
        j["_src"] = os.path.basename(j["jpegPath"])
        d[j["_src"]] = j
    return d

def Kmat(f):
    return np.array([[f["fx"],0,f["cx"]],[0,f["fy"],f["cy"]],[0,0,1]], float)

def cam_from_extrinsic(f):
    """Return (R_w2c_cv, t_w2c_cv, C_world, R_c2w_cv). Validated: reshape(4,4).T=cam2world(ARKit), then FLIP."""
    E = np.array(f["extrinsic"], float).reshape(4,4).T      # cam2world, ARKit axes
    R_c2w_arkit = E[:3,:3]
    C = E[:3,3].copy()
    R_c2w_cv = R_c2w_arkit @ FLIP                            # CV camera axes in world
    R_w2c = R_c2w_cv.T
    t_w2c = -R_w2c @ C
    return R_w2c, t_w2c, C, R_c2w_cv

# ---------------- poses ----------------
fed = load_fed()
meta = json.load(open(META))
WW, WH = meta["work_w"], meta["work_h"]           # 1024, 576
HI_W, HI_H = 3840, 2160
scale_hi = HI_W / WW                               # 3.75

poses = {}
missing_fed = []
quat_check = []
for fr in meta["frames"]:
    name = fr["name"]; src = fr["src"]
    fedj = fed.get(src)
    if fedj is None:
        missing_fed.append(src); continue
    fid = int(fedj["frameId"])
    R_w2c, t_w2c, C, R_c2w_cv = cam_from_extrinsic(fr)
    K = Kmat(fr)
    Khi = K.copy(); Khi[0,0]*=scale_hi; Khi[1,1]*=scale_hi; Khi[0,2]*=scale_hi; Khi[1,2]*=scale_hi
    # consistency: fed quaternion (CamFromWorld ARKit) vs extrinsic rotation (ARKit, before flip)
    qw,qx,qy,qz = fedj["arkitCamFromWorldQwxyz"]
    Rq = np.array([
        [1-2*(qy*qy+qz*qz), 2*(qx*qy-qz*qw),   2*(qx*qz+qy*qw)],
        [2*(qx*qy+qz*qw),   1-2*(qx*qx+qz*qz), 2*(qy*qz-qx*qw)],
        [2*(qx*qz-qy*qw),   2*(qy*qz+qx*qw),   1-2*(qx*qx+qy*qy)]])  # world2cam ARKit
    R_w2c_arkit = (np.array(fr["extrinsic"],float).reshape(4,4).T[:3,:3]).T
    quat_check.append(float(np.abs(Rq - R_w2c_arkit).max()))
    poses[str(fid)] = {
        "frameId": fid,
        "name": name,
        "src": src,
        "img_work": os.path.join(IMG_WORK, name),
        "img_highres": os.path.join(IMG_HI, src),
        "work_w": WW, "work_h": WH,
        "highres_w": HI_W, "highres_h": HI_H,
        "highres_scale": scale_hi,
        "K": K.tolist(),
        "K_highres": Khi.tolist(),
        "R_cam_from_world": R_w2c.tolist(),   # world2cam, CV (x=K[R|t]X)
        "t_cam_from_world": t_w2c.tolist(),
        "C_world": C.tolist(),
        "R_cam2world_cv": R_c2w_cv.tolist(),
        "view_dir_world": R_c2w_cv[:,2].tolist(),  # CV forward = viewing direction in world
        "arkit_quat_camfromworld_wxyz": fedj["arkitCamFromWorldQwxyz"],
        "arkit_center_world": fedj["arkitCameraCenterWorld"],
    }

conv = {
    "extrinsic_decode": "np.array(extrinsic).reshape(4,4).T  (=cam2world, ARKit axes; center in col3)",
    "axis_flip": "R_cam2world_cv = R_cam2world_arkit @ diag(1,-1,-1)",
    "projection": "x_pix = K @ (R_cam_from_world @ X_world + t_cam_from_world); depth = z of that",
    "validated": "median Sampson ~1px vs real SIFT matches (A_ceiling 0.88, B_floor 1.15) via probe_arkit_F",
    "quat_vs_extrinsic_max_abs_diff": (float(np.max(quat_check)) if quat_check else None),
}
json.dump({"convention": conv, "n_poses": len(poses), "poses": poses},
          open(OUT+"/poses.json","w"), indent=1)
print(f"[poses] {len(poses)} frames  missing_fed={len(missing_fed)}  quat_vs_ext_maxdiff={conv['quat_vs_extrinsic_max_abs_diff']:.2e}")

# ---------------- load PLY ----------------
def load_ply(path):
    f = open(path,"rb")
    hdr=b""
    while b"end_header\n" not in hdr:
        hdr += f.read(1)
    lines = hdr.decode().splitlines()
    n = next(int(l.split()[-1]) for l in lines if l.startswith("element vertex"))
    # x y z float, r g b uchar  (12 + 3 = 15 bytes)
    rec = 15
    buf = f.read(n*rec)
    xyz = np.zeros((n,3),float); rgb = np.zeros((n,3),np.uint8)
    for i in range(n):
        off=i*rec
        x,y,z = struct.unpack_from("<fff", buf, off)
        r,g,b = struct.unpack_from("<BBB", buf, off+12)
        xyz[i]=(x,y,z); rgb[i]=(r,g,b)
    return xyz, rgb
xyz, rgb = load_ply(PLY)
print(f"[ply] {len(xyz)} points  Y range [{xyz[:,1].min():.3f},{xyz[:,1].max():.3f}]")

# ---------------- floor plane ----------------
gm = json.load(open(GMASK))
n = np.array(gm["plane_n"],float); n/=np.linalg.norm(n)
pd = gm["plane_d"]
s = xyz @ n                      # signed coord along plane normal
# floor is n.X = +pd or -pd ? pick side with dense band
for val,label in [(pd,"+d"),(-pd,"-d")]:
    for th in (0.01,0.02,0.05):
        pass
cnt_plus = int((np.abs(s - pd) < 0.03).sum())
cnt_minus= int((np.abs(s + pd) < 0.03).sum())
floor_val = pd if cnt_plus >= cnt_minus else -pd
print(f"[plane] n={n.round(4).tolist()} d={pd:.4f}  band@3cm  n.X=+d:{cnt_plus}  n.X=-d:{cnt_minus} -> floor at n.X={floor_val:+.4f}")

dist = s - floor_val            # signed distance to floor plane (+ above floor along +n)
bands = {}
for th in (0.010,0.015,0.020,0.030,0.050):
    bands[f"{int(th*1000)}mm"] = int((np.abs(dist) < th).sum())
PRIMARY_TH = 0.020
floor_mask = np.abs(dist) < PRIMARY_TH
fxyz = xyz[floor_mask]; frgb = rgb[floor_mask]
print(f"[floor] bands(mm)={bands}  primary=+-{int(PRIMARY_TH*1000)}mm -> {floor_mask.sum()} pts")

# in-plane coords for area/density: build basis on plane
a = np.array([1.0,0,0]);
if abs(n@a)>0.9: a=np.array([0,0,1.0])
u = a - (a@n)*n; u/=np.linalg.norm(u); v=np.cross(n,u)
uv = np.stack([fxyz@u, fxyz@v],1)
umin,vmin = uv.min(0); umax,vmax = uv.max(0)
bbox_area = float((umax-umin)*(vmax-vmin))
# grid-cell coverage area (5cm cells) = truer footprint than bbox
cell=0.05
cells=set(map(tuple, np.floor(uv/cell).astype(int)))
cover_area = len(cells)*cell*cell
dens_bbox = floor_mask.sum()/bbox_area if bbox_area>0 else 0
dens_cover= floor_mask.sum()/cover_area if cover_area>0 else 0
thickness_std = float(dist[floor_mask].std())

def write_ply(path, P, C):
    with open(path,"wb") as f:
        f.write(b"ply\nformat binary_little_endian 1.0\n")
        f.write(f"element vertex {len(P)}\n".encode())
        f.write(b"property float x\nproperty float y\nproperty float z\n")
        f.write(b"property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
        for i in range(len(P)):
            f.write(struct.pack("<fffBBB", P[i,0],P[i,1],P[i,2], int(C[i,0]),int(C[i,1]),int(C[i,2])))
write_ply(OUT+"/production_floor.ply", fxyz, frgb)

fstats = {
    "source_ply": PLY, "total_points": int(len(xyz)),
    "plane_n_unit": n.tolist(), "plane_d_raw": pd,
    "floor_at_n_dot_X": float(floor_val),
    "sign_convention": "floor plane: n.X = floor_at_n_dot_X (= %+.4f). dist=n.X-floor_val." % floor_val,
    "band_counts": bands, "primary_band_m": PRIMARY_TH,
    "floor_points": int(floor_mask.sum()),
    "floor_frac_of_total": float(floor_mask.mean()),
    "thickness_std_m_in_band": thickness_std,
    "inplane_bbox_m": [float(umax-umin), float(vmax-vmin)],
    "bbox_area_m2": bbox_area,
    "coverage_area_m2_5cm_cells": cover_area,
    "density_pts_per_m2_bbox": dens_bbox,
    "density_pts_per_m2_coverage": dens_cover,
    "floor_centroid_world": fxyz.mean(0).tolist(),
}
json.dump(fstats, open(OUT+"/production_floor_stats.json","w"), indent=1)
print(f"[floor] cover_area={cover_area:.2f}m2 bbox={bbox_area:.2f}m2 dens_cover={dens_cover:.0f}/m2 thick_std={thickness_std*1000:.1f}mm")

# ---------------- floor frames: reproject floor points ----------------
frames_info=[]
Fpts = fxyz  # world floor points
for fid,p in poses.items():
    R=np.array(p["R_cam_from_world"]); t=np.array(p["t_cam_from_world"]); K=np.array(p["K"])
    Xc = (R @ Fpts.T).T + t
    z = Xc[:,2]
    front = z > 1e-6
    uvp = (K @ Xc.T).T
    uvp[front] /= z[front,None]
    inb = front & (uvp[:,0]>=0)&(uvp[:,0]<WW)&(uvp[:,1]>=0)&(uvp[:,1]<WH)
    vd = np.array(p["view_dir_world"])
    pitch_deg = float(np.degrees(np.arcsin(np.clip(-vd[1],-1,1))))  # +down
    frames_info.append({
        "frameId": int(fid), "name": p["name"], "src": p["src"],
        "floor_pts_in_view": int(inb.sum()),
        "floor_frac_in_view": float(inb.mean()),
        "view_pitch_down_deg": pitch_deg,
    })
frames_info.sort(key=lambda x:-x["floor_pts_in_view"])
# floor frame = sees a meaningful chunk of floor cloud
TH_PTS = 300
floor_ids = [f["frameId"] for f in frames_info if f["floor_pts_in_view"]>=TH_PTS]
json.dump({"threshold_floor_pts_in_view": TH_PTS,
           "n_floor_frames": len(floor_ids),
           "floor_frame_ids": sorted(floor_ids),
           "ranked": frames_info}, open(OUT+"/floor_frame_ids.json","w"), indent=1)

manifest={}
for f in frames_info:
    if f["frameId"] in floor_ids:
        pp=poses[str(f["frameId"])]
        manifest[str(f["frameId"])]={
            "name":pp["name"],"src":pp["src"],
            "img_work":pp["img_work"],"img_highres":pp["img_highres"],
            "floor_pts_in_view":f["floor_pts_in_view"],
            "view_pitch_down_deg":f["view_pitch_down_deg"]}
json.dump(manifest, open(OUT+"/floor_frames_manifest.json","w"), indent=1)
print(f"[frames] floor frames (>= {TH_PTS} floor pts in view): {len(floor_ids)} / {len(poses)}")
print("  top5:", [(f['frameId'],f['floor_pts_in_view'],round(f['view_pitch_down_deg'],1)) for f in frames_info[:5]])
print("  median pitch of floor frames:", round(float(np.median([f['view_pitch_down_deg'] for f in frames_info if f['frameId'] in floor_ids])),1),"deg down")
print("DONE ->", OUT)
