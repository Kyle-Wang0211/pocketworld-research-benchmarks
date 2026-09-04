"""Test inner_iterations on the finalize global BA at REAL 414-frame / 360k-point
scale (the regime the scout said inner iterations should win, unlike db50's 50
frames). One CAUCHY + DENSE_SCHUR global BA on a prebuilt model, no re-registration.
Control (double) vs use_inner_iterations. Fresh model reload each run."""
import sys, time
from pathlib import Path
import numpy as np
import pycolmap

WD = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/gpu_sfm_ab")
MODEL = WD / "tri_GPU"


def run(use_inner):
    rec = pycolmap.Reconstruction(str(MODEL))                 # fresh initial state
    opts = pycolmap.BundleAdjustmentOptions()
    opts.ceres.loss_function_type = pycolmap.LossFunctionType.CAUCHY   # production loss
    opts.ceres.loss_function_scale = 1.0
    opts.ceres.max_num_images_direct_dense_cpu_solver = 1500  # force DENSE_SCHUR @ 414
    opts.ceres.max_num_images_direct_sparse_cpu_solver = 3000  # keep dense < sparse
    so = opts.ceres.solver_options
    so.function_tolerance = 1e-6                              # gftol (production)
    so.max_num_iterations = 50                               # giter
    so.use_inner_iterations = use_inner
    so.num_threads = 8
    t0 = time.time()
    pycolmap.bundle_adjustment(rec, opts)
    dt = time.time() - t0
    errs = np.array([p.error for p in rec.points3D.values() if p.error >= 0])
    return dt, float(np.median(errs)), rec.num_points3D(), rec.num_reg_images()


if __name__ == "__main__":
    print(f"model={MODEL.name}  (CAUCHY + DENSE_SCHUR + gftol=1e-6, giter=50)")
    for label, inner in (("CONTROL(double)", False), ("INNER_ITER", True),
                         ("CONTROL(double)", False), ("INNER_ITER", True)):
        dt, rp, npts, nreg = run(inner)
        print(f"{label:18s} ba_ms={dt*1000:8.0f}  reproj_med={rp:.4f}  n_pts={npts}  n_reg={nreg}", flush=True)
