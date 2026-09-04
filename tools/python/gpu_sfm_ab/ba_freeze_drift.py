"""Rigorous check of freeze-points under REAL optimization: perturb camera poses
(inject drift), then finalize with control (all points variable) vs freeze-70%
(longest-track points constant). If freeze recovers reproj as well as control,
freezing is lossless even when the finalize has real drift to correct."""
import time
from pathlib import Path
import numpy as np
import pycolmap

WD = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/gpu_sfm_ab")
MODEL = WD / "tri_GPU"


def med_reproj(rec):
    rec.update_point_3d_errors()            # recompute from CURRENT poses (else stale cache)
    e = np.array([p.error for p in rec.points3D.values() if p.error >= 0])
    return float(np.median(e))


def perturb(rec, rot_deg, trans_frac, seed=0):
    rng = np.random.default_rng(seed)
    # scene scale for translation noise
    cens = np.array([(-im.cam_from_world().rotation.matrix().T @ im.cam_from_world().translation)
                     for im in rec.images.values()])
    scale = float(np.linalg.norm(cens.std(0)))
    for im in rec.images.values():
        p = im.cam_from_world()
        ax = rng.normal(size=3); ax /= (np.linalg.norm(ax) + 1e-9)
        ang = np.deg2rad(rot_deg) * rng.normal()
        dR = pycolmap.Rotation3d(ax * ang)                      # small-angle axis-angle
        newrot = dR * p.rotation
        newt = p.translation + rng.normal(size=3) * trans_frac * scale
        rec.frames[im.frame_id].set_cam_from_world(im.camera_id, pycolmap.Rigid3d(newrot, newt))


def opts_():
    o = pycolmap.BundleAdjustmentOptions()
    o.ceres.loss_function_type = pycolmap.LossFunctionType.CAUCHY
    o.ceres.max_num_images_direct_dense_cpu_solver = 1500
    o.ceres.max_num_images_direct_sparse_cpu_solver = 3000
    so = o.ceres.solver_options
    so.function_tolerance = 1e-6; so.max_num_iterations = 50; so.num_threads = 8
    return o


def finalize(freeze_frac, rot_deg, trans_frac):
    rec = pycolmap.Reconstruction(str(MODEL))
    perturb(rec, rot_deg, trans_frac)
    r_pre = med_reproj(rec)
    cfg = pycolmap.BundleAdjustmentConfig()
    for iid in rec.reg_image_ids():
        cfg.add_image(iid)
    pts = sorted(((pid, len(p.track.elements)) for pid, p in rec.points3D.items()), key=lambda x: -x[1])
    frozen = set(pid for pid, _ in pts[:int(len(pts) * freeze_frac)])
    for pid, _ in pts:
        (cfg.add_constant_point if pid in frozen else cfg.add_variable_point)(pid)
    cfg.fix_gauge(pycolmap.BundleAdjustmentGauge.TWO_CAMS_FROM_WORLD)
    ba = pycolmap.create_default_bundle_adjuster(opts_(), cfg, rec)
    t0 = time.time(); ba.solve(); dt = time.time() - t0
    return dt, r_pre, med_reproj(rec)


if __name__ == "__main__":
    import sys
    # sweep realistic drift levels x freeze fractions
    LEVELS = [(0.12, 0.0025)]                                 # one moderate (production-like) level
    for ROT, TRANS in LEVELS:
        print(f"\n=== drift {ROT}deg + {TRANS*100:.2f}% scene (find largest in-gate freeze) ===", flush=True)
        base = None
        for frac in (0.0, 0.2, 0.3, 0.4):
            dt, pre, post = finalize(frac, ROT, TRANS)
            if frac == 0: base = post
            tag = "control(all var)" if frac == 0 else f"freeze {int(frac*100)}%"
            dlt = "" if frac == 0 else f"  Δvs_ctrl={(post-base)/base*100:+.1f}%"
            print(f"  {tag:16s} perturbed={pre:6.3f} -> final={post:.4f}  ba_ms={dt*1000:7.0f}{dlt}", flush=True)
