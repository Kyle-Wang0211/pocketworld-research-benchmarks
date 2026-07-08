"""Export DiffMVS to CoreML (after removing aten::inverse) and benchmark it on
this Mac's CoreML runtime (compute_units=ALL -> ANE/GPU) with REAL frames at the
real 512x896 / N=5 config, for 414 iterations. Best on-device proxy without a phone.
"""
import sys, time, resource, os, shutil
from pathlib import Path
import numpy as np
import torch
import coremltools as ct
import pw_diffmvs_common as C
import pw_diffmvs_run as R

H, W, N, D = 512, 896, 5, 384
FRAMES = int(sys.argv[1]) if len(sys.argv) > 1 else 414
METHOD = sys.argv[2] if len(sys.argv) > 2 else "diffmvs"
OUT_PKG = Path(os.environ.get("AETHER_COREML_OUT", str(
    Path(__file__).resolve().parents[1] / "ios_diffmvs_bench/DiffMVSBench/DiffMVS.mlpackage")))


def real_inputs():
    man, wdef, _ = R._load_meta()
    z = np.load(R.EXPAC / "windows/win_00.npz"); fidx = wdef[0]["frame_idx"]
    view = R.select_views(z["K"], z["w2c"], fidx, 0, N)
    imgs = [torch.from_numpy(R.load_image(fidx[j]).transpose(2, 0, 1)[None]).float() for j in view]
    Ks = np.stack([R.scaled_K(z["K"][j]) for j in view])
    w2cs = np.stack([z["w2c"][j].astype("float32") for j in view])
    dmin, dmax = R.metric_depth_range(fidx[view[0]], w2cs[0])
    proj = C.make_proj_matrices(Ks, w2cs); dv = C.depth_values_tensor(dmin, dmax)
    return imgs, proj, dv


def patch_coremltools_numpy2():
    """coremltools 9.0 `_cast` does int(x.val) on a shape-[1] const array; numpy 2.x
    rejects int() on a non-0-d array -> 'only 0-dimensional arrays...'. Patch _cast to
    scalar-ize first. Fixes every aten::Int-over-array node at once."""
    from coremltools.converters.mil.frontend.torch import ops as ctops
    from coremltools.converters.mil import Builder as mb

    def _cast_fixed(context, node, dtype, dtype_name):
        x = ctops._get_inputs(context, node, expected=1)[0]
        if not (len(x.shape) == 0 or all(d == 1 for d in x.shape)):
            raise ValueError("input to cast must be scalar or length-1 tensor")
        if x.can_be_folded_to_const():
            val = x.val
            if hasattr(val, "reshape"):
                val = np.asarray(val).reshape(-1)[0]
            res = x if isinstance(val, dtype) else mb.const(val=dtype(val), name=node.name)
        elif len(x.shape) > 0:
            res = mb.cast(x=mb.squeeze(x=x, name=node.name + "_item"),
                          dtype=dtype_name, name=node.name)
        else:
            res = mb.cast(x=x, dtype=dtype_name, name=node.name)
        context.add(res, node.name)

    ctops._cast = _cast_fixed


def patch_batchnorm3d():
    """CoreML's ios17.batch_norm mis-handles rank-5 (3D) tensors -> garbage mean
    shape / LLVM error. In eval, BatchNorm == per-channel affine; replace it with
    explicit mul/add so the graph uses plain broadcast ops."""
    import torch.nn as nn

    def _bn3d_eval(self, x):
        shape = [1, x.shape[1], 1, 1, 1]
        return ((x - self.running_mean.view(shape))
                / torch.sqrt(self.running_var.view(shape) + self.eps)
                * self.weight.view(shape) + self.bias.view(shape))

    nn.BatchNorm3d.forward = _bn3d_eval


def main():
    patch_coremltools_numpy2()
    patch_batchnorm3d()
    import models.module as mod
    mod.EXPORT_MODE = True   # gather-free confidence so coremltools can convert
    # 0. verify analytic inverse == torch.inverse on affine 4x4 (bottom [0,0,0,1])
    from models.module import _invert_affine4x4
    Pr = torch.randn(4, 4, 4); Pr[:, 3, :] = torch.tensor([0., 0, 0, 1])
    err = (torch.inverse(Pr) - _invert_affine4x4(Pr)).abs().max().item()
    print(f"[verify] analytic-inverse vs torch.inverse max|err| = {err:.2e}", flush=True)
    assert err < 1e-3, "analytic inverse mismatch!"

    dev = torch.device("cpu"); model, _ = C.build_model(METHOD, dev); model.eval()
    print(f"[export] method={METHOD}", flush=True)
    imgs, proj, dv = real_inputs()

    # 1. PyTorch sanity (depth non-NaN, sane range)
    with torch.no_grad():
        out = model(imgs, proj, dv)
    d = out["depth"][-1][0].numpy(); c = out["photometric_confidence"][-1][0].numpy()
    print(f"[pytorch] depth[min,med,max]=[{d.min():.2f},{np.median(d):.2f},{d.max():.2f}] "
          f"conf med={np.median(c):.2f} NaN={np.isnan(d).any()}", flush=True)

    # 2. trace + convert
    class Wp(torch.nn.Module):
        def __init__(s, m): super().__init__(); s.m = m
        def forward(s, i0, i1, i2, i3, i4, p1, p2, p3, p4, dvv):
            o = s.m([i0, i1, i2, i3, i4], {"stage1": p1, "stage2": p2, "stage3": p3, "stage4": p4}, dvv)
            return o["depth"][-1], o["photometric_confidence"][-1]
    w = Wp(model).eval()
    names = ["i0", "i1", "i2", "i3", "i4", "p1", "p2", "p3", "p4", "dv"]
    ins = (*imgs, proj["stage1"], proj["stage2"], proj["stage3"], proj["stage4"], dv)
    with torch.no_grad():
        tr = torch.jit.trace(w, ins, check_trace=False)
    # fp32 is the DEFAULT (lossless: CPU+GPU parity 1.88%, in the run-to-run band).
    # fp16 (AETHER_COREML_FP16=1) is opt-in for a smaller/faster model at ~6% (fp16 floor).
    # compute_units=CPU_AND_GPU only: NEVER the ANE (Apple-only -> breaks cross-platform,
    # and it garbages 3D-conv/grid_sample -> 64%). CPU+GPU maps to Metal/Vulkan cross-platform.
    _prec = ct.precision.FLOAT16 if os.environ.get("AETHER_COREML_FP16") else ct.precision.FLOAT32
    ml = ct.convert(tr, inputs=[ct.TensorType(name=n, shape=x.shape) for n, x in zip(names, ins)],
                    minimum_deployment_target=ct.target.iOS17,
                    compute_units=ct.ComputeUnit.CPU_AND_GPU, compute_precision=_prec)
    shutil.rmtree(OUT_PKG, ignore_errors=True); OUT_PKG.parent.mkdir(parents=True, exist_ok=True)
    ml.save(str(OUT_PKG))
    sz = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(OUT_PKG) for f in fs) / 1e6
    print(f"[coreml] CONVERT OK  saved {OUT_PKG.name} = {sz:.2f}MB", flush=True)

    # 3. accuracy check: CoreML vs PyTorch depth
    feed = {n: x.numpy() for n, x in zip(names, ins)}
    o = ml.predict(feed)
    dk = [k for k in o if o[k].shape[-2:] == (H, W)]
    cm_depth = o[dk[0]].squeeze()
    print(f"[coreml] depth vs pytorch mean|rel|={np.mean(np.abs(cm_depth-d)/(d+1e-6)):.4f}", flush=True)

    # 4. benchmark on Mac CoreML runtime (ANE/GPU), real inputs, FRAMES iters
    for _ in range(5):
        ml.predict(feed)
    ts = []
    base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    t0 = time.time()
    for _ in range(FRAMES):
        s = time.time(); ml.predict(feed); ts.append((time.time() - s) * 1000)
    total = time.time() - t0
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
    ts.sort()
    print(f"\n=== CoreML on Mac (compute_units=ALL -> ANE/GPU), real 512x896 N=5 ===", flush=True)
    print(f"frames={FRAMES}  median={ts[len(ts)//2]:.1f}ms  p90={ts[int(len(ts)*0.9)]:.1f}ms  "
          f"min={ts[0]:.1f}ms  total={total:.1f}s", flush=True)
    print(f"process peakRSS={peak:.0f}MB (incl python/coreml runtime; model weights {sz:.1f}MB)", flush=True)


if __name__ == "__main__":
    main()
