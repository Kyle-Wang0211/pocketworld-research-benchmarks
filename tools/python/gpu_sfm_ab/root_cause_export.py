"""Root-cause the CoreML parity gap (18% vs 2.2% noise band). Seed the diffusion
noise deterministically so both forwards see IDENTICAL noise -> any residual diff is
purely SYSTEMATIC (export patches or conversion), not diffusion noise.

(b) production-PyTorch(EXPORT_MODE=False, normal BN) vs export-PyTorch(EXPORT_MODE=True
    + patched BN3d), SAME seeded noise  -> the export-patch deviation.
Then attribute: if (b) is large, the patches deviate; if (b)~0, the 18% is coremltools
conversion error (c)."""
import sys, os
from pathlib import Path
import numpy as np
import torch

BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python")
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "diffmvs"))
import pw_diffmvs_common as C
import pw_diffmvs_run as R

# ---- seed the diffusion noise: identical sequence per forward ----
_gen = torch.Generator()
_SEED = 20260708
def _seeded_randn_like(x, *a, **k):
    return torch.randn(tuple(x.shape), generator=_gen, dtype=x.dtype, device=x.device)
torch.randn_like = _seeded_randn_like


def real_inputs():
    man, wdef, _ = R._load_meta()
    z = np.load(R.EXPAC / "windows/win_00.npz"); fidx = wdef[0]["frame_idx"]
    view = R.select_views(z["K"], z["w2c"], fidx, 0, 5)
    imgs = [torch.from_numpy(R.load_image(fidx[j]).transpose(2, 0, 1)[None]).float() for j in view]
    Ks = np.stack([R.scaled_K(z["K"][j]) for j in view])
    w2cs = np.stack([z["w2c"][j].astype("float32") for j in view])
    dmin, dmax = R.metric_depth_range(fidx[view[0]], w2cs[0])
    return imgs, C.make_proj_matrices(Ks, w2cs), C.depth_values_tensor(dmin, dmax)


def rel(a, b):
    return float(np.mean(np.abs(a - b) / np.maximum(a, 1e-6)))


if __name__ == "__main__":
    import models.module as mod
    dev = torch.device("cpu")
    model, _ = C.build_model("casdiffmvs", dev); model.eval()
    imgs, proj, dv = real_inputs()

    def fwd():
        _gen.manual_seed(_SEED)               # identical noise every call
        with torch.no_grad():
            return model(imgs, proj, dv)["depth"][-1][0].numpy()

    # sanity: seeded noise makes production deterministic (two seeded runs identical)
    a, b = fwd(), fwd()
    print(f"[sanity] seeded prod run-to-run mean|rel| = {rel(a,b)*100:.4f}% (should be ~0)")

    # (production path) EXPORT_MODE=False, normal BatchNorm3d
    assert mod.EXPORT_MODE is False
    depth_prod = fwd()

    # flip to export path IN PLACE, same weights, same seeded noise
    mod.EXPORT_MODE = True
    from pw_export_coreml import patch_batchnorm3d
    patch_batchnorm3d()
    depth_exp = fwd()

    b_dev = rel(depth_prod, depth_exp)
    print(f"\n[root-cause] (b) production vs EXPORT_MODE PyTorch, SAME noise:")
    print(f"             depth mean|rel| = {b_dev*100:.2f}%   (noise band ~2.2%)")
    if b_dev > 0.05:
        print(f"  => EXPORT_MODE patches DEVIATE ~{b_dev*100:.0f}% -> the export path is NOT faithful. Fix patches.")
    elif b_dev > 0.005:
        print(f"  => small patch deviation ({b_dev*100:.1f}%); most of the 18% is coremltools conversion (c).")
    else:
        print(f"  => EXPORT_MODE patches are faithful (~0). The 18% is ENTIRELY coremltools conversion (c).")
    # per-pixel where the deviation concentrates
    d = np.abs(depth_prod - depth_exp) / np.maximum(depth_prod, 1e-6)
    print(f"[root-cause] deviation p50={np.percentile(d,50)*100:.1f}% p90={np.percentile(d,90)*100:.1f}% "
          f"p99={np.percentile(d,99)*100:.1f}% max={d.max()*100:.1f}%  frac>5%={100*(d>0.05).mean():.1f}%")
