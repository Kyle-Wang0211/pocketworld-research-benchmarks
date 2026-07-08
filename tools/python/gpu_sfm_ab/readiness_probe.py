"""Predict streaming overlap WITHOUT running inference. The fusion neighbour graph
dep(n) = {n} ∪ nearest(n, NEIGH, refs, min_base_fuse) is fully determined by camera
centres (known upfront). So ref n is fusable only once every member of dep(n) has
been inferred. This measures the readiness-delay distribution + simulates the
overlapped wall-clock, to decide if the full streaming refactor is worth building."""
import sys
from pathlib import Path
import numpy as np

BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python")
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "diffmvs"))
import pw_diffmvs_sfm_trio as T
import geom_metrics as g

pool, refs = T.build_refs()
mn, K_of, w2c_of, center_of, obs, pts_arr = T.load_model("lapa")
refs = [n for n in refs if n in center_of]
ark = g.arkit_centers_and_R()
s_al, _, _ = T.robust_align(center_of, ark)
min_base_fuse = T.MIN_BASE_FUSE_M / s_al
NEIGH = T.NEIGH
pos = {n: i for i, n in enumerate(refs)}
N = len(refs)


def nearest(n, k, cand, mb):
    c0 = center_of[n]
    d = sorted((np.linalg.norm(center_of[m] - c0), m) for m in cand if m != n)
    return [m for dist, m in d if dist >= mb][:k]


# dep(n) uses the SAME call the fusion body makes: _nearest_ctx(n, NEIGH, refs, min_base_fuse)
dep = {n: set([n]) | set(nearest(n, NEIGH, refs, min_base_fuse)) for n in refs}
# ref n fusable once its LAST-in-order dependency has been inferred (infer in refs order)
fusable_at = {n: max(pos[m] for m in dep[n]) for n in refs}   # inference step index
delay = np.array([fusable_at[n] - pos[n] for n in refs])       # how long after its own infer

print(f"\nN={N} refs  NEIGH={NEIGH}  min_base_fuse={min_base_fuse:.3f}  scale={s_al:.4f}")
print("readiness-delay (steps after a ref's own inference until it becomes fusable):")
for q in (50, 75, 90, 95, 99, 100):
    print(f"  p{q:<3d} = {np.percentile(delay, q):.0f} steps")
print(f"  mean={delay.mean():.1f}  max={delay.max()}  (max possible={N-1})")
# fraction fusable within small windows
for w in (5, 10, 20, 40, 80):
    print(f"  fusable within +{w:>2d} steps: {100*(delay <= w).mean():.0f}%")

# ---- overlap simulation: infer in refs order (t_i each), K fusion workers ----
# grounded per-ref times from the N=100 probe: inference≈0.246s/ref (MPS),
# fusion≈0.082s/ref single-thread-equiv? — use PRODUCTION full-413 numbers instead:
T_INF, T_FUSE_SER = 96.0, 57.0 * 8   # 57s was 8-worker; serial-equiv≈8x (mem-bw caps ~6)
t_inf = T_INF / N                    # per-ref inference (main thread, GPU)
t_fuse = T_FUSE_SER / N              # per-ref fusion (single worker)
for K in (4, 5, 6):
    # event sim: inference is serial on main; fusion has K workers pulling ready refs.
    # worker free-time model; a ref enters the ready queue at time fusable_at*t_inf.
    ready_time = sorted(fusable_at[n] * t_inf + t_inf for n in refs)  # when its last dep done
    workers = [0.0] * K
    finish = 0.0
    for rt in ready_time:
        w = min(range(K), key=lambda j: workers[j])
        start = max(rt, workers[w])
        workers[w] = start + t_fuse
        finish = max(finish, workers[w])
    seq = T_INF + T_FUSE_SER / min(6, K)   # rough serial-two-pass (fusion at K, mem-bw~6 cap)
    # more honest baseline: production measured 96 + 57 (8w) = 153 for infer+fuse
    base = 96.0 + 57.0
    print(f"K={K}: overlapped infer+fuse wall≈{finish:.1f}s   vs two-pass {base:.0f}s   "
          f"saved≈{base - finish:.1f}s ({100*(base-finish)/base:.0f}%)")
print("(sim uses production 96s infer / 57s(8w) fuse; per-ref uniform; ignores contention)")
