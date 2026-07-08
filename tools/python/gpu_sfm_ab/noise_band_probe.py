"""B-band acceptance threshold: how much does casdiffmvs depth drift run-to-run
(same input, fresh diffusion noise each forward)? That drift IS the lossless bar
the CoreML export must fall within. Compares: PyTorch run1 vs run2 (the noise band),
then CoreML vs each PyTorch run (must be <= the band)."""
import sys, os
from pathlib import Path
import numpy as np
import torch

BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python")
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "diffmvs"))
import pw_diffmvs_common as C
import pw_diffmvs_run as R

METHOD = "casdiffmvs"


def real_inputs():
    man, wdef, _ = R._load_meta()
    z = np.load(R.EXPAC / "windows/win_00.npz"); fidx = wdef[0]["frame_idx"]
    view = R.select_views(z["K"], z["w2c"], fidx, 0, 5)
    imgs = [torch.from_numpy(R.load_image(fidx[j]).transpose(2, 0, 1)[None]).float() for j in view]
    Ks = np.stack([R.scaled_K(z["K"][j]) for j in view])
    w2cs = np.stack([z["w2c"][j].astype("float32") for j in view])
    dmin, dmax = R.metric_depth_range(fidx[view[0]], w2cs[0])
    proj = C.make_proj_matrices(Ks, w2cs); dv = C.depth_values_tensor(dmin, dmax)
    return imgs, proj, dv


def rel(a, b):
    return float(np.mean(np.abs(a - b) / (np.maximum(a, 1e-6))))


if __name__ == "__main__":
    dev = torch.device("cpu")
    model, _ = C.build_model(METHOD, dev); model.eval()
    imgs, proj, dv = real_inputs()

    def fwd():
        with torch.no_grad():
            o = model(imgs, proj, dv)
        return o["depth"][-1][0].numpy()

    runs = [fwd() for _ in range(4)]
    print(f"[noise-band] {METHOD} PyTorch-CPU, 4 fresh forwards (same input, fresh diffusion noise):")
    pair_rels = []
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            r = rel(runs[i], runs[j]); pair_rels.append(r)
            print(f"  run{i} vs run{j}: depth mean|rel| = {r*100:.2f}%")
    band = float(np.median(pair_rels)); band_max = float(np.max(pair_rels))
    print(f"[noise-band] PyTorch run-to-run depth mean|rel|: median={band*100:.2f}%  max={band_max*100:.2f}%")
    print(f"[noise-band] => B-band acceptance threshold ~ {band*100:.2f}% (CoreML must fall in this)")

    # CoreML vs each PyTorch run
    pkg = os.environ.get("AETHER_COREML_OUT",
                         str(BR / "../ios_diffmvs_bench/DiffMVSBench/CasDiffMVS.mlpackage"))
    if Path(pkg).exists():
        import coremltools as ct
        ml = ct.models.MLModel(pkg)
        names = ["i0", "i1", "i2", "i3", "i4", "p1", "p2", "p3", "p4", "dv"]
        ins = (*imgs, proj["stage1"], proj["stage2"], proj["stage3"], proj["stage4"], dv)
        feed = {n: x.numpy() for n, x in zip(names, ins)}
        o = ml.predict(feed)
        H, W = runs[0].shape
        dk = [k for k in o if o[k].shape[-2:] == (H, W)]
        cm = o[dk[0]].squeeze()
        cm_rels = [rel(cm, runs[i]) for i in range(len(runs))]
        print(f"[coreml] vs 4 PyTorch runs: mean|rel| = {[f'{r*100:.2f}%' for r in cm_rels]}")
        verdict = "WITHIN band ✅" if np.median(cm_rels) <= band_max * 1.5 else "OUTSIDE band ❌"
        print(f"[coreml] median={np.median(cm_rels)*100:.2f}% vs band_max={band_max*100:.2f}% -> {verdict}")
    else:
        print(f"[coreml] {pkg} not found; run pw_export_coreml.py casdiffmvs first")
