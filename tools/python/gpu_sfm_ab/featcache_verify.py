"""Verify the FeatureNet cross-ref cache is BYTE-IDENTICAL to recomputing.
FeatureNet has no RNG (eval convs) → caching it doesn't change the diffusion RNG
trajectory → same seed => identical depth/conf. Same 12 refs with overlapping
views (frames recur), no-cache vs cache, compare arrays + count FeatureNet calls."""
import sys, time
from pathlib import Path
import numpy as np
import torch

BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks")
sys.path.insert(0, str(BR / "tools/python"))
import pw_diffmvs_common as C
import pw_diffmvs_sfm_trio as T

dev = C.pick_device("mps")
model, _ = C.build_model(T.METHOD, dev)

# count FeatureNet calls
_orig_feat = model.feature.forward
_calls = [0]
def _counting_feat(x):
    _calls[0] += 1
    return _orig_feat(x)
model.feature.forward = _counting_feat

mnames, K_of, w2c_of, center_of, obs, pts_arr = T.load_model("lapa")
pool = [n for n in mnames][:50]
refs = pool[:40]

def nearest(n, k):
    c0 = center_of[n]
    d = sorted((np.linalg.norm(center_of[m] - c0), m) for m in pool if m != n)
    return [m for _, m in d[:k]]

def build(n):
    view = [n] + nearest(n, T.NVIEW - 1)
    imgs = [T.R.load_image(T.name2mi_map()[m]).transpose(2, 0, 1) for m in view]
    Ks = np.stack([K_of[m] for m in view]); w2cs = np.stack([w2c_of[m] for m in view])
    proj = C.make_proj_matrices(Ks, w2cs); dv = C.depth_values_tensor(0.4, 5.0)
    return view, imgs, proj, dv


def run(use_cache):
    torch.manual_seed(0)
    fc = {} if use_cache else None
    _calls[0] = 0
    out = {}
    # warm once (build views + first inference) then time the rest
    if dev.type == "mps":
        torch.mps.synchronize()
    t0 = time.time()
    for n in refs:
        view, imgs, proj, dv = build(n)
        d, c, _ = C.run_inference(model, imgs, proj, dv, dev,
                                  view_names=(view if use_cache else None),
                                  feat_cache=fc)
        out[n] = (d, c)
    if dev.type == "mps":
        torch.mps.synchronize()
    return out, _calls[0], (len(fc) if fc is not None else None), time.time() - t0


run(True)  # warm the graph/model once (exclude one-time compile from timing)
print("=== no-cache (baseline) ===", flush=True)
o0, calls0, _, wall0 = run(False)
print(f"FeatureNet calls (no-cache): {calls0} ({len(refs)}x{T.NVIEW})  wall={wall0:.1f}s")
print("=== with cache ===", flush=True)
o1, calls1, ncached, wall1 = run(True)
print(f"FeatureNet calls (cache): {calls1}  cached: {ncached}  wall={wall1:.1f}s "
      f"({100*(1-wall1/wall0):.0f}% faster)")

alleq = True
for n in refs:
    de = np.array_equal(o0[n][0], o1[n][0]); ce = np.array_equal(o0[n][1], o1[n][1])
    if not (de and ce):
        alleq = False
        print(f"  MISMATCH {n}: depth_eq={de} conf_eq={ce} "
              f"maxdiff={np.abs(o0[n][0]-o1[n][0]).max():.2e}")
print(f"\nRESULT: {'BYTE-IDENTICAL PASS' if alleq else 'MISMATCH FAIL'}  "
      f"FeatureNet calls {calls0} -> {calls1} ({100*(1-calls1/calls0):.0f}% fewer)")
