"""Step 1: spatial-first pair selection over the 66 floor frames.
Keep pairs that are (a) covisible (view-dir angle < VIEW_ANG_MAX) and
(b) WIDE ENOUGH baseline to give real floor parallax -- the critical fix vs the
low-parallax depth-slide trap (adjacent frames tri deg std 3.35m). kNN within a
baseline WINDOW, not raw nearest neighbours."""
import json, itertools
import numpy as np
from fr_common import (FLOOR_IDS, C_of, vdir_of, PLANE_N, FLOOR_VAL, FR)

VIEW_ANG_MAX = 60.0     # deg between view directions (covisibility)
B_MIN, B_MAX = 0.15, 3.5  # m baseline window (>0.15 => >~2deg floor parallax @2-3m)
KNN = 16                # per frame keep up to K nearest covisible in-window partners

def ang(a, b):
    c = np.clip(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)), -1, 1)
    return np.degrees(np.arccos(c))

def est_floor_parallax(i, j):
    """Rough parallax angle (deg) at the floor plane for a mid-ray of frame i.
    Intersect frame i optical axis with floor plane, get depth; parallax~=baseline/depth."""
    Ci = C_of(i); di = vdir_of(i)
    denom = di @ PLANE_N
    if abs(denom) < 1e-6: return 0.0
    s = (FLOOR_VAL - Ci @ PLANE_N) / denom   # ray param to floor plane
    if s <= 0: return 0.0
    Xf = Ci + s * di                          # floor hit point
    b = np.linalg.norm(C_of(i) - C_of(j))
    depth = np.linalg.norm(Xf - Ci)
    return np.degrees(np.arctan2(b, depth)), b, depth

def main():
    ids = sorted(FLOOR_IDS)
    C = {i: C_of(i) for i in ids}
    V = {i: vdir_of(i) for i in ids}
    pairs = set()
    per_frame_stats = []
    for i in ids:
        cand = []
        for j in ids:
            if j == i: continue
            b = np.linalg.norm(C[i] - C[j])
            if not (B_MIN <= b <= B_MAX): continue
            if ang(V[i], V[j]) > VIEW_ANG_MAX: continue
            cand.append((b, j))
        cand.sort()
        keep = cand[:KNN]
        per_frame_stats.append({"frame": i, "n_covis_in_window": len(cand), "kept": len(keep)})
        for b, j in keep:
            pairs.add((min(i, j), max(i, j)))
    pairs = sorted(pairs)
    # diagnostics
    par, base, dep = [], [], []
    rows = []
    for i, j in pairs:
        p, b, d = est_floor_parallax(i, j)
        par.append(p); base.append(b); dep.append(d)
        rows.append({"i": i, "j": j, "baseline_m": round(b, 3),
                     "view_ang_deg": round(ang(V[i], V[j]), 1),
                     "est_floor_parallax_deg": round(p, 2)})
    par = np.array(par); base = np.array(base)
    print(f"[pairs] floor_frames={len(ids)} -> pairs={len(pairs)}")
    print(f"[pairs] baseline m: min {base.min():.3f} med {np.median(base):.3f} max {base.max():.3f}")
    print(f"[pairs] est floor parallax deg: min {par.min():.2f} med {np.median(par):.2f} "
          f"max {par.max():.2f}  frac>=2deg {(par>=2).mean():.2f}")
    json.dump({"config": {"view_ang_max": VIEW_ANG_MAX, "b_min": B_MIN, "b_max": B_MAX, "knn": KNN},
               "n_floor_frames": len(ids), "n_pairs": len(pairs), "pairs": rows},
              open(FR + "/fr_pairs_B.json", "w"), indent=1)
    print(f"[pairs] wrote fr_pairs.json ({len(pairs)} pairs)")

if __name__ == "__main__":
    main()
