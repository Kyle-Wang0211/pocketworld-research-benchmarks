"""Precise MPS hotspot profiling of a SINGLE-ref CasDiffMVS forward (5 views,
512x896). Goal: verify (do NOT assume) the batch-agent's claim that the
"bandwidth bottleneck is in the DDIM cost-volume / grid_sample".

Reuses batch_probe.py's setup (load_model + build_inputs at B=1). Runs THREE
complementary measurements because this torch build (2.12) exposes NO
ProfilerActivity.MPS -> torch.profiler cannot see Metal kernel time
(self_device_time_total == 0); its CPU numbers are ASYNC DISPATCH cost, not GPU
time. The reliable GPU signal on MPS is torch.mps.synchronize()-fenced wall.

  (1) torch.profiler(CPU, record_shapes): op INVENTORY, call counts, input
      shapes, CPU-dispatch ranking. Honest caveat: device time unavailable.
  (2) sync-fenced PER-STAGE decomposition: FeatureNet(x5 views) / ContextNet /
      Stage1 InitialCost (1/8, 3D-conv cost vol) / Stage2 DDIM 3 iters (1/4) /
      Stage3 DDIM 3 iters (1/2). Wrap each submodule.forward w/ sync-fence.
  (3) sync-fenced PER-OP-FAMILY accumulate: monkeypatch F.grid_sample /
      F.conv2d / F.conv3d / F.conv_transpose3d to fence each call and sum its
      ISOLATED device ms. grid_sample keyed by src-feature spatial size so the
      1/8 vs 1/4 vs 1/2 (=stage) split falls out. This is the true op-level GPU
      attribution the profiler can't give.

MPS timing is non-deterministic + thermal-drifts (host wall var +-30%); every
number is a MEDIAN over many reps, and shares (ratios) are more trustworthy than
absolute ms. Run:
  KMP_DUPLICATE_LIB_OK=TRUE python3.11 gpu_sfm_ab/profile_probe.py [REPS]
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
import torch
import torch.nn.functional as F
from torch.profiler import profile, ProfilerActivity

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 15
NVIEW = T.NVIEW

# ── setup (mirror batch_probe.py) ────────────────────────────────────────────
print(f"[profile_probe] METHOD={T.METHOD} NVIEW={NVIEW} REPS={REPS}", flush=True)
mn, K_of, w2c_of, center_of, obs, pts_arr = T.load_model("lapa")
name2mi = T.name2mi_map()

z = np.load(T.OUT / "p1cache_trio_7full.npz", allow_pickle=True)
fr = z["frames"].tolist()
_zr = z["drange"]
drng = {n: (float(_zr[i][0]), float(_zr[i][1])) for i, n in enumerate(fr)}
z.close()

pool = [n for n in fr if n in K_of and n in center_of]
refs = [n for n in pool if n in drng]
assert refs, "no ref with drange"
ref = refs[0]


def nearest(n, k):
    c0 = center_of[n]
    d = sorted((float(np.linalg.norm(center_of[m] - c0)), m) for m in pool if m != n)
    return [m for _, m in d[:k]]


view = [ref] + nearest(ref, NVIEW - 1)
img_cache = {m: R.load_image(name2mi[m]).transpose(2, 0, 1).astype(np.float32) for m in view}
H, W = img_cache[view[0]].shape[1:]
print(f"[profile_probe] ref={ref} views={view} img={H}x{W}", flush=True)

dev = C.pick_device("mps")
model, _ = C.build_model(T.METHOD, dev)
print(f"[profile_probe] model on {dev.type}", flush=True)


def sync():
    if dev.type == "mps":
        torch.mps.synchronize()


# build inputs ONCE (outside timed region): imgs list of (1,3,H,W), proj, dv
imgs = [torch.from_numpy(img_cache[m][None]).float().to(dev) for m in view]
Ks = np.stack([K_of[m] for m in view]); w2cs = np.stack([w2c_of[m] for m in view])
proj = {s: v.to(dev) for s, v in C.make_proj_matrices(Ks, w2cs).items()}
dmin, dmax = drng[ref]
dv = C.depth_values_tensor(dmin, dmax).to(dev)


@torch.no_grad()
def fwd():
    return model(imgs, proj, dv)


# ── warmup (graph compile excluded) ──────────────────────────────────────────
print("[profile_probe] warming…", flush=True)
for _ in range(6):
    _ = fwd(); sync()


def med(xs):
    return float(np.median(xs)) if xs else float("nan")


# clean un-instrumented full-forward wall (the denominator for all shares)
clean = []
for _ in range(REPS):
    sync(); t0 = time.time(); _ = fwd(); sync(); clean.append((time.time() - t0) * 1e3)
CLEAN_MS = med(clean)
print(f"[profile_probe] clean full-forward: median={CLEAN_MS:.1f} ms "
      f"(min={min(clean):.1f} max={max(clean):.1f} n={len(clean)})", flush=True)

# ── (1) torch.profiler: op inventory + counts + shapes (CPU dispatch only) ────
print("\n[profile_probe] (1) torch.profiler — CPU dispatch (device time N/A on this MPS build)…",
      flush=True)
acts = [ProfilerActivity.CPU]
if hasattr(ProfilerActivity, "MPS"):
    acts.append(ProfilerActivity.MPS)
with profile(activities=acts, record_shapes=True) as prof:
    for _ in range(REPS):
        _ = fwd()
    sync()
ka = prof.key_averages()
dev_seen = any(e.self_device_time_total > 0 for e in ka)
print(f"[profile_probe] profiler device activity captured: {dev_seen} "
      f"(False => CPU dispatch only; use fenced device ms below)", flush=True)
rows = sorted(ka, key=lambda e: e.self_cpu_time_total, reverse=True)
prof_top = []
tot_cpu = sum(e.self_cpu_time_total for e in ka) or 1.0
print(f"{'op':32s} {'self_cpu_us':>12s} {'cpu%':>6s} {'calls':>7s}", flush=True)
for e in rows[:22]:
    pct = 100.0 * e.self_cpu_time_total / tot_cpu
    print(f"{e.key[:32]:32s} {e.self_cpu_time_total:12.1f} {pct:6.1f} {e.count:7d}", flush=True)
    prof_top.append(dict(op=e.key, self_cpu_us=e.self_cpu_time_total, cpu_pct=pct,
                         calls=e.count))

# grid_sampler shape variants (call-count per resolution) via shape-averages
try:
    kag = prof.key_averages(group_by_input_shape=True)
    print("\n[profile_probe] grid_sampler_2d shape variants (calls per resolution):",
          flush=True)
    gs_shapes = []
    for e in kag:
        if "grid_sampler_2d" in e.key:
            shp = str(e.input_shapes)
            print(f"  calls={e.count:3d} self_cpu_us={e.self_cpu_time_total:9.1f} shapes={shp}",
                  flush=True)
            gs_shapes.append(dict(calls=e.count, self_cpu_us=e.self_cpu_time_total, shapes=shp))
except Exception as ex:
    gs_shapes = []
    print(f"  (shape grouping unavailable: {ex})", flush=True)

# ── (2) per-STAGE sync-fenced decomposition ──────────────────────────────────
print("\n[profile_probe] (2) per-stage sync-fenced decomposition…", flush=True)
stage_acc = {}          # name -> list of ms (one entry per rep, summed over calls in that rep)
_rep_tmp = {}


def wrap_module(mod, name):
    orig = mod.forward

    def timed(*a, **k):
        sync(); t0 = time.time()
        out = orig(*a, **k)
        sync(); _rep_tmp[name] = _rep_tmp.get(name, 0.0) + (time.time() - t0) * 1e3
        return out
    mod.forward = timed
    return orig


orig_feat = wrap_module(model.feature, "FeatureNet(x5 views)")
orig_ctx = wrap_module(model.context, "ContextNet")
orig_dn = wrap_module(model.depthnet, "Stage1_InitialCost_1/8")
orig_u0 = wrap_module(model.update_block[0], "Stage2_DDIM_3iter_1/4")
orig_u1 = wrap_module(model.update_block[1], "Stage3_DDIM_3iter_1/2")
STAGES = ["FeatureNet(x5 views)", "ContextNet", "Stage1_InitialCost_1/8",
          "Stage2_DDIM_3iter_1/4", "Stage3_DDIM_3iter_1/2"]

inst_total = []
for _ in range(REPS):
    _rep_tmp.clear()
    sync(); t0 = time.time(); _ = fwd(); sync()
    inst_total.append((time.time() - t0) * 1e3)
    for s in STAGES:
        stage_acc.setdefault(s, []).append(_rep_tmp.get(s, 0.0))

# restore
model.feature.forward = orig_feat; model.context.forward = orig_ctx
model.depthnet.forward = orig_dn; model.update_block[0].forward = orig_u0
model.update_block[1].forward = orig_u1

INST_MS = med(inst_total)
stage_ms = {s: med(stage_acc[s]) for s in STAGES}
sum_stage = sum(stage_ms.values())
other_ms = max(0.0, INST_MS - sum_stage)   # scale_inv_depth, upsample, interpolate, glue
print(f"[profile_probe] instrumented total median={INST_MS:.1f} ms "
      f"(sync-fence overhead vs clean {CLEAN_MS:.1f})", flush=True)
print(f"{'stage':26s} {'ms':>8s} {'% of clean':>11s} {'% of instr':>11s}", flush=True)
stage_report = []
for s in STAGES:
    m = stage_ms[s]
    print(f"{s:26s} {m:8.1f} {100*m/CLEAN_MS:10.1f}% {100*m/INST_MS:10.1f}%", flush=True)
    stage_report.append(dict(stage=s, ms=m, pct_clean=100*m/CLEAN_MS, pct_instr=100*m/INST_MS))
print(f"{'other(glue/upsample/interp)':26s} {other_ms:8.1f} {100*other_ms/CLEAN_MS:10.1f}% "
      f"{100*other_ms/INST_MS:10.1f}%", flush=True)
stage_report.append(dict(stage="other(glue/upsample/interp)", ms=other_ms,
                         pct_clean=100*other_ms/CLEAN_MS, pct_instr=100*other_ms/INST_MS))
DDIM6_MS = stage_ms["Stage2_DDIM_3iter_1/4"] + stage_ms["Stage3_DDIM_3iter_1/2"]
print(f"[profile_probe] 6 DDIM iters (stage2+stage3) = {DDIM6_MS:.1f} ms "
      f"= {100*DDIM6_MS/CLEAN_MS:.1f}% of clean", flush=True)

# ── (3) per-OP-FAMILY sync-fenced accumulate (true isolated device ms) ────────
print("\n[profile_probe] (3) per-op-family sync-fenced accumulate…", flush=True)
fam = {}      # name -> [ms per rep]; grid_sample keyed by stage-resolution
_fam_tmp = {}
_orig_gs = F.grid_sample
_orig_c2 = F.conv2d
_orig_c3 = F.conv3d
_orig_ct3 = F.conv_transpose3d


def _acc(name, dt):
    _fam_tmp[name] = _fam_tmp.get(name, 0.0) + dt


def gs_patch(inp, grid, *a, **k):
    # src feature spatial size identifies the stage: 1/8=(64,112) 1/4=(128,224) 1/2=(256,448)
    hw = tuple(inp.shape[-2:])
    tag = {(64, 112): "1/8(stage1)", (128, 224): "1/4(stage2)",
           (256, 448): "1/2(stage3)"}.get(hw, str(hw))
    sync(); t0 = time.time(); out = _orig_gs(inp, grid, *a, **k); sync()
    _acc(f"grid_sample::{tag}", (time.time() - t0) * 1e3)
    return out


def c2_patch(*a, **k):
    sync(); t0 = time.time(); out = _orig_c2(*a, **k); sync()
    _acc("conv2d", (time.time() - t0) * 1e3); return out


def c3_patch(*a, **k):
    sync(); t0 = time.time(); out = _orig_c3(*a, **k); sync()
    _acc("conv3d", (time.time() - t0) * 1e3); return out


def ct3_patch(*a, **k):
    sync(); t0 = time.time(); out = _orig_ct3(*a, **k); sync()
    _acc("conv_transpose3d", (time.time() - t0) * 1e3); return out


count_probe = {"done": False}


def install():
    F.grid_sample = gs_patch; F.conv2d = c2_patch
    F.conv3d = c3_patch; F.conv_transpose3d = ct3_patch


def restore():
    F.grid_sample = _orig_gs; F.conv2d = _orig_c2
    F.conv3d = _orig_c3; F.conv_transpose3d = _orig_ct3


# also count calls once (via a counting-only pass, no fence) for the report
call_counts = {}
_cs_gs, _cs_c2, _cs_c3, _cs_ct3 = F.grid_sample, F.conv2d, F.conv3d, F.conv_transpose3d


def _cnt(nm):
    call_counts[nm] = call_counts.get(nm, 0) + 1


F.grid_sample = lambda inp, grid, *a, **k: (_cnt("grid_sample::" + {
    (64, 112): "1/8(stage1)", (128, 224): "1/4(stage2)",
    (256, 448): "1/2(stage3)"}.get(tuple(inp.shape[-2:]), str(tuple(inp.shape[-2:])))),
    _cs_gs(inp, grid, *a, **k))[1]
F.conv2d = lambda *a, **k: (_cnt("conv2d"), _cs_c2(*a, **k))[1]
F.conv3d = lambda *a, **k: (_cnt("conv3d"), _cs_c3(*a, **k))[1]
F.conv_transpose3d = lambda *a, **k: (_cnt("conv_transpose3d"), _cs_ct3(*a, **k))[1]
_ = fwd(); sync()
F.grid_sample, F.conv2d, F.conv3d, F.conv_transpose3d = _cs_gs, _cs_c2, _cs_c3, _cs_ct3

# now the timed accumulate passes
install()
famA_total = []
for _ in range(REPS):
    _fam_tmp.clear()
    sync(); t0 = time.time(); _ = fwd(); sync()
    famA_total.append((time.time() - t0) * 1e3)
    for nm, v in _fam_tmp.items():
        fam.setdefault(nm, []).append(v)
restore()

FAMINST_MS = med(famA_total)
fam_ms = {nm: med(v) for nm, v in fam.items()}
gs_total = sum(v for nm, v in fam_ms.items() if nm.startswith("grid_sample"))
conv3d_all = fam_ms.get("conv3d", 0.0) + fam_ms.get("conv_transpose3d", 0.0)
conv2d_all = fam_ms.get("conv2d", 0.0)
fam_sum = sum(fam_ms.values())
fam_other = max(0.0, FAMINST_MS - fam_sum)   # elementwise/concat/softmax/interp/matmul + fence gaps

print(f"[profile_probe] family-instrumented total median={FAMINST_MS:.1f} ms", flush=True)
print(f"{'op family':26s} {'ms':>8s} {'% clean':>9s} {'calls':>7s}", flush=True)
fam_report = []
for nm in sorted(fam_ms, key=lambda k: -fam_ms[k]):
    m = fam_ms[nm]; c = call_counts.get(nm, 0)
    print(f"{nm:26s} {m:8.1f} {100*m/CLEAN_MS:8.1f}% {c:7d}", flush=True)
    fam_report.append(dict(op=nm, ms=m, pct_clean=100*m/CLEAN_MS, calls=c))
# aggregate rows
agg = [("grid_sample(ALL)", gs_total, sum(call_counts.get(k, 0) for k in call_counts if k.startswith("grid_sample"))),
       ("conv2d(ALL)", conv2d_all, call_counts.get("conv2d", 0)),
       ("conv3d+deconv3d(cost-vol reg)", conv3d_all,
        call_counts.get("conv3d", 0) + call_counts.get("conv_transpose3d", 0)),
       ("elementwise/other(remainder)", fam_other, 0)]
print("  --- aggregates ---", flush=True)
for nm, m, c in agg:
    print(f"{nm:32s} {m:8.1f} ms  {100*m/CLEAN_MS:6.1f}% clean  calls={c}", flush=True)

# ── verdict math ─────────────────────────────────────────────────────────────
gs_share = 100 * gs_total / CLEAN_MS
ddim_share = 100 * DDIM6_MS / CLEAN_MS
conv3d_share = 100 * conv3d_all / CLEAN_MS
feat_share = 100 * stage_ms["FeatureNet(x5 views)"] / CLEAN_MS
conv2d_share = 100 * conv2d_all / CLEAN_MS
print("\n================ VERDICT ================", flush=True)
print(f"clean full-forward (single ref, 5 views, {H}x{W}): {CLEAN_MS:.1f} ms", flush=True)
print(f"grid_sample (ALL 28 warps):        {gs_total:6.1f} ms  {gs_share:5.1f}% of forward", flush=True)
print(f"  grid_sample 1/8 (stage1):        {fam_ms.get('grid_sample::1/8(stage1)',0):6.1f} ms", flush=True)
print(f"  grid_sample 1/4 (stage2 DDIM):   {fam_ms.get('grid_sample::1/4(stage2)',0):6.1f} ms", flush=True)
print(f"  grid_sample 1/2 (stage3 DDIM):   {fam_ms.get('grid_sample::1/2(stage3)',0):6.1f} ms", flush=True)
print(f"6 DDIM iters (stage2+stage3):      {DDIM6_MS:6.1f} ms  {ddim_share:5.1f}% of forward", flush=True)
print(f"cost-vol 3D conv (InitialCost reg):{conv3d_all:6.1f} ms  {conv3d_share:5.1f}% of forward", flush=True)
print(f"FeatureNet (x5 views):             {stage_ms['FeatureNet(x5 views)']:6.1f} ms  {feat_share:5.1f}% of forward", flush=True)
print(f"conv2d (ALL, feat+ctx+UNet+GRU):   {conv2d_all:6.1f} ms  {conv2d_share:5.1f}% of forward", flush=True)

out = dict(
    method=T.METHOD, img=[H, W], nview=NVIEW, reps=REPS,
    profiler_device_captured=bool(dev_seen),
    clean_ms=CLEAN_MS, instrumented_ms=INST_MS, family_instrumented_ms=FAMINST_MS,
    stages=stage_report, ddim6_ms=DDIM6_MS, ddim6_pct=ddim_share,
    families=fam_report,
    grid_sample_ms=gs_total, grid_sample_pct=gs_share,
    grid_sample_by_stage={k: fam_ms[k] for k in fam_ms if k.startswith("grid_sample")},
    conv3d_costvol_ms=conv3d_all, conv3d_costvol_pct=conv3d_share,
    conv2d_ms=conv2d_all, conv2d_pct=conv2d_share,
    featurenet_ms=stage_ms["FeatureNet(x5 views)"], featurenet_pct=feat_share,
    elementwise_remainder_ms=fam_other,
    call_counts=call_counts,
    profiler_top_cpu=prof_top, grid_sample_shapes=gs_shapes,
)
outp = BR / "gpu_sfm_ab" / "profile_probe_result.json"
json.dump(out, open(outp, "w"), indent=2, default=float)
print(f"\n[profile_probe] wrote {outp}", flush=True)
