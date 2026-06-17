"""Align GLOMAP sparse cloud into COLMAP's frame via shared camera centers
(Umeyama similarity), so the 4 SfM versions overlay in one coordinate system.
"""
import numpy as np, open3d as o3d
from pathlib import Path

HERE = Path(__file__).resolve().parent


def quat_to_R(q):
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
        [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
        [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def parse_centers(images_txt):
    centers = {}
    lines = [l for l in open(images_txt) if not l.startswith("#") and l.strip()]
    for i in range(0, len(lines), 2):                 # every 2nd line = pose line
        p = lines[i].split()
        if len(p) < 10:
            continue
        q = list(map(float, p[1:5])); t = np.array(list(map(float, p[5:8])))
        name = p[9]
        R = quat_to_R(q)
        centers[name] = -R.T @ t                       # camera center in world
    return centers


def umeyama(src, dst):                                 # src->dst similarity (s,R,t)
    mu_s, mu_d = src.mean(0), dst.mean(0)
    S, D = src - mu_s, dst - mu_d
    cov = D.T @ S / len(src)
    U, d, Vt = np.linalg.svd(cov)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1; R = U @ Vt
    var = (S ** 2).sum() / len(src)
    s = np.trace(np.diag(d)) / var
    t = mu_d - s * R @ mu_s
    return s, R, t


cC = parse_centers(HERE / "txt_colmap/images.txt")
cG = parse_centers(HERE / "txt_glomap/images.txt")
common = sorted(set(cC) & set(cG))
src = np.array([cG[n] for n in common]); dst = np.array([cC[n] for n in common])
s, R, t = umeyama(src, dst)
resid = np.linalg.norm((s * (R @ src.T).T + t) - dst, axis=1)
print(f"common cams={len(common)} similarity scale={s:.3f} align resid median={np.median(resid):.4f} max={resid.max():.4f}")

for name in ["glomap", "glomap_ba"]:
    pc = o3d.io.read_point_cloud(str(HERE / f"{name}.ply"))
    P = np.asarray(pc.points)
    pc.points = o3d.utility.Vector3dVector((s * (R @ P.T).T + t))
    out = HERE / f"{name}_aligned.ply"
    o3d.io.write_point_cloud(str(out), pc)
    print(f"wrote {out.name} ({len(P):,} pts, in COLMAP frame)")
