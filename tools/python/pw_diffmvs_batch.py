"""Batch DiffMVS over several PocketWorld reference frames + the BEDROCK test:
does photometric_confidence collapse on low-texture image regions?

Quantitative test (frame-cherry-pick-proof): bin every valid pixel by local
image texture (std of luma in a 7x7 window) and report mean confidence per bin.
Hypothesis HOLDS iff confidence rises monotonically with texture and is clearly
low in the lowest-texture bin (textureless floor / glossy / wall).
"""
from __future__ import annotations
import sys
import numpy as np
import cv2
import pw_diffmvs_common as C
import pw_diffmvs_run as R

# spread refs across the sequence; windows are spatially-ordered, frame0 of each
PAIRS = [(0, 0), (4, 0), (8, 0), (12, 0), (16, 0), (20, 0), (26, 0), (32, 0)]
METHOD = sys.argv[1] if len(sys.argv) > 1 else "diffmvs"
DEVP = sys.argv[2] if len(sys.argv) > 2 else "cpu"


def local_texture(rgb_u8: np.ndarray, k: int = 7) -> np.ndarray:
    g = cv2.cvtColor(rgb_u8, cv2.COLOR_RGB2GRAY).astype(np.float32)
    mean = cv2.blur(g, (k, k))
    sq = cv2.blur(g * g, (k, k))
    return np.sqrt(np.clip(sq - mean * mean, 0, None))   # local std of luma


def main():
    dev = C.pick_device(DEVP)
    model, _ = C.build_model(METHOD, dev)
    tex_all, conf_all = [], []
    times = []
    for win, ref in PAIRS:
        try:
            res = R.run_one(win, ref, 5, DEVP, METHOD, model=model, dev=dev)
        except Exception as e:
            print(f"  win{win} ref{ref} FAILED: {type(e).__name__} {str(e)[:120]}")
            continue
        times.append(res["dt"])
        tex = local_texture(res["ref_rgb"])
        conf = res["conf"]
        m = (res["depth"] > 0) & np.isfinite(conf)
        tex_all.append(tex[m].ravel()); conf_all.append(conf[m].ravel())

    tex_all = np.concatenate(tex_all); conf_all = np.concatenate(conf_all)
    print("\n=== BEDROCK TEST: confidence vs local image texture ===")
    print(f"pixels={len(tex_all):,}  device={dev}  warm-mean-dt={np.mean(times[1:]):.2f}s "
          f"(first={times[0]:.2f}s)")
    # texture bins by percentile so each bin has equal mass
    qs = np.percentile(tex_all, [0, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100])
    print(f"{'texture-bin (luma std)':>26} | {'mean conf':>9} | {'%>0.5':>6} | {'%<0.3':>6}")
    for i in range(len(qs) - 1):
        lo, hi = qs[i], qs[i + 1]
        sel = (tex_all >= lo) & (tex_all <= hi if i == len(qs) - 2 else tex_all < hi)
        c = conf_all[sel]
        if len(c) == 0:
            continue
        print(f"{f'[{lo:6.1f},{hi:6.1f}]':>26} | {c.mean():9.3f} | "
              f"{100*(c>0.5).mean():6.1f} | {100*(c<0.3).mean():6.1f}")
    # correlation
    r = np.corrcoef(tex_all, conf_all)[0, 1]
    lowtex = conf_all[tex_all <= qs[1]]; hightex = conf_all[tex_all >= qs[-2]]
    print(f"\nPearson r(texture, conf) = {r:+.3f}")
    print(f"lowest-texture bin: mean conf {lowtex.mean():.3f}  | highest-texture bin: {hightex.mean():.3f}")
    print(f"VERDICT cue: hypothesis HOLDS if r>0 and lowtex<<hightex; "
          f"ratio low/high = {lowtex.mean()/max(hightex.mean(),1e-6):.2f}")


if __name__ == "__main__":
    main()
