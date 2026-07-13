"""Shared geometry/config for the cap50 LoFTR floor-rescue pipeline.
All poses are CV-convention (already validated ~1px Sampson) straight from poses.json:
  x_pix = K @ (R_cam_from_world @ X_world + t_cam_from_world)
No production code touched. Pure numpy + (cv2 for MAGSAC/PLY only)."""
import os, json, subprocess
import numpy as np

SP = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/b3b899a4-8125-4eb7-a21a-eb3d48c3d2a8/scratchpad"
FR = SP + "/floor_rescue"

# ---- load poses / floor frames ----
_P = json.load(open(FR + "/poses.json"))
POSES = {int(k): v for k, v in _P["poses"].items()}
_FF = json.load(open(FR + "/floor_frame_ids.json"))
FLOOR_IDS = list(_FF["floor_frame_ids"])
_STATS = json.load(open(FR + "/production_floor_stats.json"))
PLANE_N = np.array(_STATS["plane_n_unit"], float); PLANE_N /= np.linalg.norm(PLANE_N)
FLOOR_VAL = float(_STATS["floor_at_n_dot_X"])     # n.X on the floor plane (= -1.3597)

# ---- match resolution (reduced from 1024x576 to keep LoFTR MPS peak << 4.7GB) ----
WORK_W, WORK_H = 1024, 576          # coordinate frame that K belongs to
# LoFTR input (÷8 ok); keypoints scaled back to WORK. Override via env FR_MW/FR_MH.
# Keep 16:9 aspect (WORK is 16:9) so a single isotropic scale maps back cleanly.
MATCH_W = int(os.environ.get("FR_MW", "640"))
MATCH_H = int(os.environ.get("FR_MH", "360"))

# ---- gates ----
SAMPSON_T = 3.0        # px, ARKit-F epipolar reject (independent of planar degeneracy)
MAGSAC_T  = 3.0        # px, cv2 USAC_MAGSAC F reject (#14)
REPROJ_T  = 3.0        # px, #2 triangulation gate (max reproj over views); also < #3's 4px
TRI_ANGLE_MIN = 2.0    # deg, #2/#3 parallax gate (kills low-parallax depth-slide)
DEPTH_MIN, DEPTH_MAX = 0.05, 30.0   # m, cheirality + range
GRID = 8               # px, #12 hloc quantization cell (work-res)
FLOOR_BAND = 0.020     # m, primary production floor band (headline metric)

PAGE = 16384
def avail_gb():
    out = subprocess.check_output(["vm_stat"]).decode(); d = {}
    for ln in out.splitlines():
        if ":" in ln and "Pages" in ln:
            k, v = ln.split(":"); d[k.strip()] = int(v.strip().rstrip("."))
    return (d.get("Pages free", 0) + d.get("Pages speculative", 0) + d.get("Pages inactive", 0)) * PAGE / 1e9

def K_of(fid):    return np.array(POSES[fid]["K"], float)
def R_of(fid):    return np.array(POSES[fid]["R_cam_from_world"], float)
def t_of(fid):    return np.array(POSES[fid]["t_cam_from_world"], float)
def C_of(fid):    return np.array(POSES[fid]["C_world"], float)
def vdir_of(fid): return np.array(POSES[fid]["view_dir_world"], float)
def imgpath(fid): return POSES[fid]["img_work"]

def projmat(fid):
    return K_of(fid) @ np.hstack([R_of(fid), t_of(fid).reshape(3, 1)])

def skew(t):
    return np.array([[0, -t[2], t[1]], [t[2], 0, -t[0]], [-t[1], t[0], 0]])

def F_arkit(i, j):
    """Fundamental mapping img_i -> img_j from independent ARKit poses."""
    Ri, ti = R_of(i), t_of(i); Rj, tj = R_of(j), t_of(j)
    R_rel = Rj @ Ri.T
    t_rel = tj - R_rel @ ti
    E = skew(t_rel) @ R_rel
    return np.linalg.inv(K_of(j)).T @ E @ np.linalg.inv(K_of(i))

def sampson(F, p0, p1):
    if len(p0) == 0: return np.zeros(0)
    p0h = np.hstack([p0, np.ones((len(p0), 1))]); p1h = np.hstack([p1, np.ones((len(p1), 1))])
    Fp0 = (F @ p0h.T).T; Ftp1 = (F.T @ p1h.T).T
    num = np.sum(p1h * Fp0, axis=1) ** 2
    den = Fp0[:, 0]**2 + Fp0[:, 1]**2 + Ftp1[:, 0]**2 + Ftp1[:, 1]**2
    return np.sqrt(num / (den + 1e-12))

def floor_dist(X):
    """signed distance to floor plane (m); |.|<FLOOR_BAND => in production band."""
    return X @ PLANE_N - FLOOR_VAL

def write_ply(path, xyz, rgb=None, extra=None, extra_names=None):
    n = len(xyz)
    hdr = ["ply", "format ascii 1.0", f"element vertex {n}",
           "property float x", "property float y", "property float z"]
    if rgb is not None:
        hdr += ["property uchar red", "property uchar green", "property uchar blue"]
    if extra is not None:
        for nm in extra_names:
            hdr.append(f"property float {nm}")
    hdr += ["end_header"]
    with open(path, "w") as f:
        f.write("\n".join(hdr) + "\n")
        for i in range(n):
            row = f"{xyz[i,0]:.6f} {xyz[i,1]:.6f} {xyz[i,2]:.6f}"
            if rgb is not None:
                row += f" {int(rgb[i,0])} {int(rgb[i,1])} {int(rgb[i,2])}"
            if extra is not None:
                row += " " + " ".join(f"{extra[i,k]:.4f}" for k in range(extra.shape[1]))
            f.write(row + "\n")
