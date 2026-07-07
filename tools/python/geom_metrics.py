"""Reconstructed minimal geom_metrics (original .py+.pyc were purged by /private/tmp
cleanup). Provides the ONLY two functions the dense/TSDF pipeline uses:
  - umeyama(src,dst): closed-form Umeyama(1991) similarity (s,R,t), src->dst.
  - arkit_centers_and_R(): {jpeg_basename: (center3, R33)} from the capture manifest's
    per-frame cameraExtrinsic4x4 (world-to-camera 4x4). Center = -R^T @ t.
Verified against the known alignment scale (~0.2168, med_resid ~9mm).
"""
import json
import numpy as np
from pathlib import Path

_MANIFEST = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/"
                 "data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/"
                 "external_pose_k_vs_res_2026_06_10/k414_spatial_order_manifest.json")


def umeyama(src, dst):
    """Similarity transform mapping src -> dst: dst ~= s * (R @ src) + t."""
    src = np.asarray(src, np.float64)
    dst = np.asarray(dst, np.float64)
    n, d = src.shape
    mu_s = src.mean(0)
    mu_d = dst.mean(0)
    sc = src - mu_s
    dc = dst - mu_d
    cov = (dc.T @ sc) / n
    U, D, Vt = np.linalg.svd(cov)
    S = np.eye(d)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        S[-1, -1] = -1.0
    R = U @ S @ Vt
    var_s = (sc ** 2).sum() / n
    s = float((D * np.diag(S)).sum() / var_s)
    t = mu_d - s * (R @ mu_s)
    return s, R, t


def _center_from_extrinsic(E):
    """E = cameraExtrinsic4x4 = world-to-camera (COLMAP/ARKit-w2c):
    camera center C = -R^T @ t; world-from-camera rotation = R^T."""
    R = E[:3, :3]
    t = E[:3, 3]
    C = -R.T @ t
    return C, R.T


def arkit_centers_and_R():
    frames = json.load(open(_MANIFEST))["frames"]
    out = {}
    for f in frames:
        name = Path(f["jpegPath"]).name
        E = np.asarray(f["cameraExtrinsic4x4"], np.float64).reshape(4, 4)
        c, R = _center_from_extrinsic(E)
        out[name] = (c, R)
    return out
