"""Fresh lever #1: freeze the most-stable (longest-track) 3D points as CONSTANT
in the finalize global BA. Points STAY in the problem (still give camera
residuals); only their coords are fixed -> removed from the Schur point-block
elimination (dominant cost of a 360k-point dome solve). Distinct from rejected
COVGAIN/track-cap (those DELETE points). A/B on prebuilt 414-frame tri_GPU:
control (all variable) vs freeze top-frac longest-track. CAUCHY + DENSE_SCHUR."""
import sys, time
from pathlib import Path
import numpy as np
import pycolmap

WD = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/gpu_sfm_ab")
MODEL = WD / "tri_GPU"


def opts_():
    o = pycolmap.BundleAdjustmentOptions()
    o.ceres.loss_function_type = pycolmap.LossFunctionType.CAUCHY
    o.ceres.loss_function_scale = 1.0
    o.ceres.max_num_images_direct_dense_cpu_solver = 1500
    o.ceres.max_num_images_direct_sparse_cpu_solver = 3000
    so = o.ceres.solver_options
    so.function_tolerance = 1e-6
    so.max_num_iterations = 50
    so.num_threads = 8
    return o


def run(freeze_frac):
    rec = pycolmap.Reconstruction(str(MODEL))            # fresh initial state
    cfg = pycolmap.BundleAdjustmentConfig()
    for iid in rec.reg_image_ids():
        cfg.add_image(iid)
    pts = sorted(((pid, len(p.track.elements)) for pid, p in rec.points3D.items()),
                 key=lambda x: -x[1])
    n_freeze = int(len(pts) * freeze_frac)
    frozen = set(pid for pid, _ in pts[:n_freeze])
    for pid, _ in pts:
        if pid in frozen:
            cfg.add_constant_point(pid)
        else:
            cfg.add_variable_point(pid)
    cfg.fix_gauge(pycolmap.BundleAdjustmentGauge.TWO_CAMS_FROM_WORLD)
    ba = pycolmap.create_default_bundle_adjuster(opts_(), cfg, rec)
    t0 = time.time()
    ba.solve()
    dt = time.time() - t0
    errs = np.array([p.error for p in rec.points3D.values() if p.error >= 0])
    return dt, float(np.median(errs)), rec.num_points3D(), n_freeze


if __name__ == "__main__":
    print(f"model={MODEL.name}  CAUCHY+DENSE_SCHUR gftol=1e-6 giter=50", flush=True)
    for frac in (0.0, 0.3, 0.5, 0.7):
        dt, rp, npts, nfz = run(frac)
        tag = "control(all var)" if frac == 0 else f"freeze {int(frac*100)}%"
        print(f"{tag:18s} ba_ms={dt*1000:8.0f}  reproj_med={rp:.4f}  n_pts={npts}  n_frozen={nfz}", flush=True)
