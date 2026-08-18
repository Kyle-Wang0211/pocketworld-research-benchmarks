"""Robust (trimmed) Umeyama align of v6 GLOMAP -> regular COLMAP frame.
v6's gauge has a few outlier camera centers that wrecked the plain fit
(scale 0.001). Iteratively drop high-residual pairs, refit."""
import numpy as np, open3d as o3d
from pathlib import Path
H = Path(__file__).resolve().parent


def quat_to_R(q):
    w, x, y, z = q
    return np.array([[1-2*(y*y+z*z), 2*(x*y-w*z), 2*(x*z+w*y)],
                     [2*(x*y+w*z), 1-2*(x*x+z*z), 2*(y*z-w*x)],
                     [2*(x*z-w*y), 2*(y*z+w*x), 1-2*(x*x+y*y)]])


def centers(p):
    o = {}
    L = [l for l in open(p) if not l.startswith("#") and l.strip()]
    for i in range(0, len(L), 2):
        s = L[i].split()
        if len(s) < 10:
            continue
        o[s[9]] = -quat_to_R(list(map(float, s[1:5]))).T @ np.array(list(map(float, s[5:8])))
    return o


def umeyama(src, dst):
    ms, md = src.mean(0), dst.mean(0)
    S, D = src-ms, dst-md
    U, d, Vt = np.linalg.svd(D.T@S/len(src))
    R = U@Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1; R = U@Vt
    s = np.trace(np.diag(d))/((S**2).sum()/len(src))
    return s, R, md-s*R@ms


cC, cG = centers(H.parent/"txt_colmap/images.txt"), centers(H/"txt_glomap/images.txt")
common = sorted(set(cC) & set(cG))
src = np.array([cG[n] for n in common]); dst = np.array([cC[n] for n in common])
keep = np.ones(len(src), bool)
for it in range(6):
    s, R, t = umeyama(src[keep], dst[keep])
    res = np.linalg.norm((s*(R@src.T).T+t)-dst, axis=1)
    thr = np.median(res[keep])*3 + 1e-9
    newkeep = res < thr
    print(f"iter{it}: kept {keep.sum()}->{newkeep.sum()} scale={s:.3f} medRes={np.median(res[keep]):.4f}")
    if newkeep.sum() == keep.sum() or newkeep.sum() < 50:
        keep = newkeep; break
    keep = newkeep
s, R, t = umeyama(src[keep], dst[keep])
res = np.linalg.norm((s*(R@src.T).T+t)-dst, axis=1)
print(f"FINAL scale={s:.3f} kept={keep.sum()}/{len(src)} medRes={np.median(res[keep]):.4f}")
pc = o3d.io.read_point_cloud(str(H/"glomap_hd_raw.ply")); P = np.asarray(pc.points)
pc.points = o3d.utility.Vector3dVector(s*(R@P.T).T+t)
o3d.io.write_point_cloud(str(H/"glomap_v8.ply"), pc)
print(f"wrote glomap_v8.ply ({len(P):,} pts)")
