"""Align glomap_hd_raw.ply into COLMAP-HD frame via shared camera centers -> glomap_prod.ply."""
import numpy as np, open3d as o3d
from pathlib import Path
H = Path(__file__).resolve().parent


def quat_to_R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def centers(images_txt):
    out = {}
    L = [l for l in open(images_txt) if not l.startswith("#") and l.strip()]
    for i in range(0, len(L), 2):
        p = L[i].split()
        if len(p) < 10:
            continue
        q = list(map(float, p[1:5])); t = np.array(list(map(float, p[5:8])))
        out[p[9]] = -quat_to_R(q).T @ t
    return out


def umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0)
    S, D = src-ms, dst-md
    U, d, Vt = np.linalg.svd(D.T @ S / len(src))
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1; R = U @ Vt
    s = np.trace(np.diag(d)) / ((S**2).sum()/len(src))
    return s, R, md - s*R@ms


cC, cG = centers(H.parent/"txt_colmap/images.txt"), centers(H/"txt_glomap/images.txt")  # dst = regular COLMAP frame (page overlay)
common = sorted(set(cC) & set(cG))
src = np.array([cG[n] for n in common]); dst = np.array([cC[n] for n in common])
s, R, t = umeyama(src, dst)
resid = np.linalg.norm((s*(R@src.T).T+t)-dst, axis=1)
print(f"HD align: common={len(common)} scale={s:.3f} resid med={np.median(resid):.4f}")
pc = o3d.io.read_point_cloud(str(H/"glomap_hd_raw.ply"))
P = np.asarray(pc.points)
pc.points = o3d.utility.Vector3dVector(s*(R@P.T).T+t)
o3d.io.write_point_cloud(str(H/"glomap_prod.ply"), pc)
print(f"wrote glomap_prod.ply ({len(P):,} pts)")
