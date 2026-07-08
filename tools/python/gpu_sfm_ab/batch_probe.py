"""Prototype: cross-ref BATCHED DiffMVS inference (B>1) vs the per-ref B=1 path.

Question: the DiffMVS/CasDiffMVS net is extremely narrow (base_channels=8). At B=1
the MPS/mobile GPU is badly under-occupied. Stacking K refs (each 5 views) into the
BATCH dim and running ONE forward should raise occupancy -> higher throughput.

What this measures, same process, back-to-back (relative gain is robust to the
±30% thermal-drift wall-clock noise on this host; absolute ms is not):
  1. throughput: forward-only ms/ref at B = 1,2,4,8 (interleaved rounds, median)
  2. peak MPS memory (torch.mps.driver_allocated_memory) per B
  3. bit-parity: does each ref's B>1 depth equal its B=1 depth?

PARITY vs the diffusion noise: CasDiffMVS injects torch.randn_like noise twice per
forward (one DDIM step in each of the 2 refine stages). That RNG is the real cause
of the "cross-run point count drifts by tens of thousands" the team saw — NOT the
graph. So the *fair* batch-parity test must feed each ref the SAME noise regardless
of B. We monkeypatch torch.randn_like to draw per-sample noise seeded ONLY by
(ref_seed, call_index) — independent of batch size and batch position. Then any
B=1-vs-B>1 difference is pure batching-machinery numerics (conv/warp/matmul tiling).
Timing runs use the REAL (unseeded) randn so throughput is production-representative.

The model forward is used UNMODIFIED (no wrapper edit) — it already carries B end to
end (differentiable_warping uses B=src_fea.shape[0]; depth_values[:,0].view(-1,...);
InitialCost/GetCost/DDIM all per-batch). The only "wrapper" is input assembly:
per-ref proj/dv are stacked along batch so each sample keeps its own views+drange.

Run:
  KMP_DUPLICATE_LIB_OK=TRUE python3.11 gpu_sfm_ab/batch_probe.py [N] [ROUNDS]
"""
import os, sys, time, json
from pathlib import Path
import numpy as np

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
for _v in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

BR = Path("/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python")
sys.path.insert(0, str(BR)); sys.path.insert(0, str(BR / "diffmvs"))

import pw_diffmvs_sfm_trio as T
import pw_diffmvs_run as R
import pw_diffmvs_common as C

# child mode: measure ONE batch size's peak MPS memory in a FRESH process so the
# caching-allocator high-water is not polluted by other batch sizes -> clean peak.
MEMCHILD = (len(sys.argv) > 1 and sys.argv[1] == "memchild")
if MEMCHILD:
    N = int(sys.argv[3]); ROUNDS = 0; MEM_B = int(sys.argv[2])
    B_LIST = [MEM_B]
else:
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 48
    ROUNDS = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    B_LIST = [1, 2, 4, 8]
NVIEW = T.NVIEW  # 5

import torch

# ─────────────────────────────────────────────────────────────────────────────
# Seeded per-sample noise: makes torch.randn_like batch-invariant so the parity
# test isolates the deterministic graph. Draw on CPU (portable/deterministic),
# then move to the tensor's device. Seed depends ONLY on the sample's ref_seed and
# the intra-forward call index -> sample b gets identical noise for any B / offset.
_orig_randn_like = torch.randn_like
_NOISE = {"seeds": None, "call": 0}


def _seeded_randn_like(x, *a, **k):
    seeds = _NOISE["seeds"]
    if seeds is None:
        return _orig_randn_like(x, *a, **k)
    call = _NOISE["call"]; _NOISE["call"] += 1
    B = x.shape[0]
    assert len(seeds) == B, f"seeds {len(seeds)} != B {B}"
    single = list(x.shape); single[0] = 1
    parts = []
    for b in range(B):
        torch.manual_seed(int(seeds[b]) * 1_000_003 + call * 7919 + 12345)
        parts.append(torch.randn(single, dtype=x.dtype))  # CPU
    return torch.cat(parts, 0).to(x.device)


torch.randn_like = _seeded_randn_like  # active only when _NOISE["seeds"] is set


def _set_noise(seeds):
    _NOISE["seeds"] = seeds
    _NOISE["call"] = 0


# ─────────────────────────────────────────────────────────────────────────────
def mps_mem_mb():
    if hasattr(torch.mps, "driver_allocated_memory"):
        return torch.mps.driver_allocated_memory() / 2**20
    return float("nan")


def empty_cache():
    if hasattr(torch.mps, "empty_cache"):
        torch.mps.empty_cache()


# ── setup: model dump + frozen dranges + view lists ──────────────────────────
print(f"[batch_probe] N={N} ROUNDS={ROUNDS} B_LIST={B_LIST} NVIEW={NVIEW} "
      f"METHOD={T.METHOD}", flush=True)
mn, K_of, w2c_of, center_of, obs, pts_arr = T.load_model("lapa")
name2mi = T.name2mi_map()

z = np.load(T.OUT / "p1cache_trio_7full.npz", allow_pickle=True)
fr = z["frames"].tolist()
_zr = z["drange"]
drng = {n: (float(_zr[i][0]), float(_zr[i][1])) for i, n in enumerate(fr)}
z.close()

pool = [n for n in fr if n in K_of and n in center_of]           # source candidates
refs = [n for n in pool if n in drng][:N]                        # the N refs we probe
assert len(refs) == N, f"only {len(refs)} refs available (< {N})"


def nearest(n, k):
    c0 = center_of[n]
    d = sorted((float(np.linalg.norm(center_of[m] - c0)), m) for m in pool if m != n)
    return [m for _, m in d[:k]]


# fixed, deterministic view list per ref (ref + NVIEW-1 nearest sources)
view_of = {n: [n] + nearest(n, NVIEW - 1) for n in refs}
seed_of = {n: i for i, n in enumerate(refs)}                     # stable per-ref seed

# preload every image used, once
need = sorted({m for n in refs for m in view_of[n]})
img_cache = {m: R.load_image(name2mi[m]).transpose(2, 0, 1).astype(np.float32) for m in need}
H, W = img_cache[need[0]].shape[1:]
print(f"[batch_probe] refs={len(refs)} unique_frames_loaded={len(need)} img={H}x{W}", flush=True)

dev = C.pick_device("mps")
model, _ = C.build_model(T.METHOD, dev)
print(f"[batch_probe] model on {dev.type}", flush=True)


# ── batched input assembly + forward (built OUTSIDE the timed region) ─────────
def build_inputs(batch_refs):
    """Stack K refs along batch. imgs: NVIEW tensors each (K,3,H,W). proj: per-stage
    (K,NVIEW,2,4,4). dv: (K,384). Each sample keeps its OWN proj + drange."""
    K = len(batch_refs)
    imgs = []
    for v in range(NVIEW):
        arr = np.stack([img_cache[view_of[n][v]] for n in batch_refs])   # (K,3,H,W)
        imgs.append(torch.from_numpy(arr).float().to(dev))
    projs = {"stage1": [], "stage2": [], "stage3": [], "stage4": []}
    dvs = []
    for n in batch_refs:
        view = view_of[n]
        Ks = np.stack([K_of[m] for m in view]); w2cs = np.stack([w2c_of[m] for m in view])
        pm = C.make_proj_matrices(Ks, w2cs)          # each (1,NVIEW,2,4,4)
        for s in projs:
            projs[s].append(pm[s])
        dmin, dmax = drng[n]
        dvs.append(C.depth_values_tensor(dmin, dmax))  # (1,384)
    proj = {s: torch.cat(v, 0).to(dev) for s, v in projs.items()}
    dv = torch.cat(dvs, 0).to(dev)
    return imgs, proj, dv


@torch.no_grad()
def forward_depths(imgs, proj, dv):
    out = model(imgs, proj, dv)
    return out["depth"][-1]          # (B,H,W) on device


if MEMCHILD:
    # isolated clean peak for one batch size: warm once, then peak over 3 chunks
    empty_cache()
    hi = mps_mem_mb()
    ok = True
    try:
        for rep in range(4):                       # rep 0 = warm (compile)
            for o in range(0, min(len(refs), MEM_B * 3), MEM_B):
                chunk = refs[o:o + MEM_B]
                imgs = []
                for v in range(NVIEW):
                    arr = np.stack([img_cache[view_of[n][v]] for n in chunk])
                    imgs.append(torch.from_numpy(arr).float().to(dev))
                projs = {"stage1": [], "stage2": [], "stage3": [], "stage4": []}
                dvs = []
                for n in chunk:
                    view = view_of[n]
                    Ks = np.stack([K_of[m] for m in view]); w2cs = np.stack([w2c_of[m] for m in view])
                    pm = C.make_proj_matrices(Ks, w2cs)
                    for s in projs:
                        projs[s].append(pm[s])
                    dmin, dmax = drng[n]; dvs.append(C.depth_values_tensor(dmin, dmax))
                proj = {s: torch.cat(v, 0).to(dev) for s, v in projs.items()}
                dv = torch.cat(dvs, 0).to(dev)
                _NOISE["seeds"] = None
                _ = forward_depths(imgs, proj, dv)
                if dev.type == "mps":
                    torch.mps.synchronize()
                hi = max(hi, mps_mem_mb())
    except Exception as e:
        ok = False
        print(f"MEMCHILD_FAIL B={MEM_B} {type(e).__name__}: {e}", flush=True)
    print(f"MEMRESULT B={MEM_B} peak_mb={hi:.1f} ok={ok}", flush=True)
    sys.exit(0)


@torch.no_grad()
def run_sweep_timed(B, seeded=False):
    """Forward-only wall over all N refs in chunks of B. Inputs built between timed
    segments so the measured time is pure GPU forward. Returns (ms_per_ref, depths?)."""
    total = 0.0
    depths = {} if seeded else None
    for o in range(0, len(refs), B):
        chunk = refs[o:o + B]
        imgs, proj, dv = build_inputs(chunk)
        if seeded:
            _set_noise([seed_of[n] for n in chunk])
        else:
            _NOISE["seeds"] = None
        if dev.type == "mps":
            torch.mps.synchronize()
        t0 = time.time()
        d = forward_depths(imgs, proj, dv)
        if dev.type == "mps":
            torch.mps.synchronize()
        total += time.time() - t0
        if seeded:
            dn = d.detach().float().cpu().numpy()
            for i, n in enumerate(chunk):
                depths[n] = dn[i].copy()
    return total * 1000.0 / len(refs), depths


# ── warm every batch shape (graph compile excluded from timing) ──────────────
print("[batch_probe] warming graphs…", flush=True)
for B in B_LIST:
    try:
        run_sweep_timed(B, seeded=False)
    except Exception as e:
        print(f"[warm] B={B} FAILED: {type(e).__name__}: {e}", flush=True)
empty_cache()

# ── 1) PARITY: B=1 baseline (seeded) vs each B>1 (seeded), per-ref bitwise ────
print("\n[batch_probe] PARITY (seeded noise = batch-invariant)…", flush=True)
_, base = run_sweep_timed(1, seeded=True)
# determinism self-check: re-run B=1, must be byte-identical
_, base2 = run_sweep_timed(1, seeded=True)
det_ok = all(np.array_equal(base[n], base2[n]) for n in refs)
print(f"[parity] B=1 self-determinism (seeded, back-to-back): {'OK' if det_ok else 'FAIL'}",
      flush=True)

parity = {}
for B in B_LIST:
    if B == 1:
        continue
    _, dB = run_sweep_timed(B, seeded=True)
    max_abs = 0.0; n_exact = 0; max_rel = 0.0
    for n in refs:
        a, b = base[n], dB[n]
        if np.array_equal(a, b):
            n_exact += 1
        diff = np.abs(a - b)
        max_abs = max(max_abs, float(diff.max()))
        denom = np.maximum(np.abs(a), 1e-6)
        max_rel = max(max_rel, float((diff / denom).max()))
    kind = ("byte-identical" if n_exact == len(refs)
            else "fp-noise" if max_rel < 1e-3 else "DIVERGENT")
    parity[B] = dict(exact=n_exact, total=len(refs), max_abs=max_abs,
                     max_rel=max_rel, kind=kind)
    print(f"[parity] B={B}: exact={n_exact}/{len(refs)} max_abs={max_abs:.3e} "
          f"max_rel={max_rel:.3e} -> {kind}", flush=True)

# ── 2) THROUGHPUT: interleaved rounds (real noise), median ms/ref ────────────
print("\n[batch_probe] THROUGHPUT (real noise, interleaved rounds)…", flush=True)
samples = {B: [] for B in B_LIST}
for r in range(ROUNDS):
    for B in B_LIST:
        try:
            mpr, _ = run_sweep_timed(B, seeded=False)
            samples[B].append(mpr)
            print(f"[time] round {r} B={B}: {mpr:.1f} ms/ref", flush=True)
        except Exception as e:
            print(f"[time] round {r} B={B} FAILED: {type(e).__name__}: {e}", flush=True)

# ── 3) MEMORY: per-B CLEAN peak, each in a FRESH subprocess (no allocator
#      high-water pollution across batch sizes) ────────────────────────────────
print("\n[batch_probe] MEMORY (clean peak per B, fresh subprocess each)…", flush=True)
import subprocess, re
peak_mb = {}
for B in B_LIST:
    try:
        env = dict(os.environ); env["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        r = subprocess.run([sys.executable, __file__, "memchild", str(B), str(N)],
                           capture_output=True, text=True, env=env, timeout=600)
        m = re.search(r"MEMRESULT B=\d+ peak_mb=([\d.]+) ok=(\w+)", r.stdout)
        if m and m.group(2) == "True":
            peak_mb[B] = float(m.group(1))
            print(f"[mem] B={B}: peak={peak_mb[B]:.0f} MB", flush=True)
        else:
            peak_mb[B] = None
            tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
            print(f"[mem] B={B} FAILED: {tail}", flush=True)
    except Exception as e:
        peak_mb[B] = None
        print(f"[mem] B={B} subprocess error: {type(e).__name__}: {e}", flush=True)

# ── report ───────────────────────────────────────────────────────────────────
def med(xs):
    return float(np.median(xs)) if xs else float("nan")


b1 = med(samples[1])
print("\n================ SUMMARY ================", flush=True)
print(f"{'B':>3} {'ms/ref(med)':>12} {'gain x':>8} {'peak MB':>9} {'MB/ref':>8} {'parity':>16}",
      flush=True)
rows = []
for B in B_LIST:
    m = med(samples[B])
    gain = (b1 / m) if (m == m and m > 0) else float("nan")
    pk = peak_mb.get(B)
    mbref = (pk / B) if pk else float("nan")
    pk_s = f"{pk:.0f}" if pk else "OOM/FAIL"
    par = "baseline" if B == 1 else parity.get(B, {}).get("kind", "n/a")
    rows.append((B, m, gain, pk, mbref, par))
    print(f"{B:>3} {m:>12.1f} {gain:>8.2f} {pk_s:>9} {mbref:>8.0f} {par:>16}", flush=True)

# iPhone jetsam ~3072 MB app budget -> flag which B fits (peak MB is the model's
# own MPS footprint; add ~app overhead on device -> conservative)
print("\niPhone constraint (jetsam ~3072 MB app RSS budget):", flush=True)
for B, m, gain, pk, mbref, par in rows:
    if pk is None:
        note = "did not run"
    elif pk < 2500:
        note = "fits with headroom"
    elif pk < 3072:
        note = "tight"
    else:
        note = "EXCEEDS budget"
    print(f"  B={B}: peak~{'%.0f' % pk if pk else 'n/a'} MB -> {note}", flush=True)

out = dict(N=N, ROUNDS=ROUNDS, method=T.METHOD, img=[H, W],
           det_ok=bool(det_ok),
           throughput={B: dict(ms_per_ref=med(samples[B]),
                               gain_vs_B1=(b1 / med(samples[B])) if samples[B] else None,
                               samples=samples[B]) for B in B_LIST},
           peak_mb={B: peak_mb.get(B) for B in B_LIST},
           parity=parity)
outp = BR / "gpu_sfm_ab" / "batch_probe_result.json"
json.dump(out, open(outp, "w"), indent=2, default=float)
print(f"\n[batch_probe] wrote {outp}", flush=True)
