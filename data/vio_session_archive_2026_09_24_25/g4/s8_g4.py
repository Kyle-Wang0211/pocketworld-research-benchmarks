import sys, json, pickle, numpy as np
from g4lib import *
OFFS = (-2, -1, 0, 1, 2)

def eval_curve(run, poses):
    return {o: ratios_of(run.measure(poses, off=o)) for o in OFFS}

def summ(cr):
    c, amin = g4_from_curve(cr)
    r0 = cr[0][np.isfinite(cr[0])]
    return dict(curve={str(o): float(v) for o, v in c.items()}, argmin=amin, n0=int(len(r0)),
                k=float(1/np.median(r0)) if len(r0) else float('nan'), between0=float(c[0]))

def boot_argmin(cr, B=2000, block=None, seed=0):
    rng = np.random.default_rng(seed); n = len(cr[0]); cnt = {o: 0 for o in OFFS}
    M = np.vstack([cr[o] for o in OFFS])
    for _ in range(B):
        if block:
            starts = rng.integers(0, n - block + 1, int(np.ceil(n / block)))
            idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        else:
            idx = rng.integers(0, n, n)
        c = {o: between_iqr(M[i, idx][np.isfinite(M[i, idx])]) for i, o in enumerate(OFFS)}
        cnt[min(c, key=c.get)] += 1
    return {str(o): v / B for o, v in cnt.items()}

def aligned_xr(run):
    """XR 世界系 → ARKit 世界系(Sim3 的 R,t;**保留 XR 自己的尺度**,只做刚体)。"""
    s, Ra, ta, _ = sim3_align(run.xr, run.ark)
    return {t: (Ra @ R, Ra @ (s * np.asarray(C)) + ta) for t, (R, C) in run.xr.items()}, s

def work(key):
    run = Run(key)
    out = {'key': key}
    cr_a = eval_curve(run, run.ark); cr_x = eval_curve(run, run.xr)
    out['arkit'] = summ(cr_a); out['xr'] = summ(cr_x)
    for nm, cr in (('arkit', cr_a), ('xr', cr_x)):
        out[nm]['boot_iid'] = boot_argmin(cr)
        out[nm]['boot_block5'] = boot_argmin(cr, block=5)
    # SNR:深度偏移引入的逐对比值变化 d_o = r_ark,o / r_ark,0 的离散度 vs 轨迹自身逐对离散度
    def rs(x):
        x = np.log(x[np.isfinite(x)]); q1, q3 = np.percentile(x, [25, 75]); return (q3 - q1)
    out['snr'] = {o: float(rs(cr_a[o] / cr_a[0])) for o in (-2, -1, 1, 2)}
    out['snr']['xr_log_iqr0'] = float(rs(cr_x[0])); out['snr']['ark_log_iqr0'] = float(rs(cr_a[0]))
    # 混合轨迹
    xa, s_x = aligned_xr(run)
    common = [t for t in run.ark if t in xa]
    hyb_rx = {t: (xa[t][0], run.ark[t][1]) for t in common}                 # XR 旋转 + ARKit 中心
    hyb_cx = {t: (run.ark[t][0], xa[t][1]) for t in common}                 # ARKit 旋转 + XR 中心
    out['hyb_xrRot_arkC'] = summ(eval_curve(run, hyb_rx))
    out['hyb_arkRot_xrC'] = summ(eval_curve(run, hyb_cx))
    # 合成对照:ARKit + 循环平移的 XR 残差(整段 30 Hz 残差序列,在子集帧上取)
    Afull = all_arkit(run); Xfull = all_xr(run)
    s_f, R_f, t_f, _ = sim3_align(Xfull, Afull)
    ts = [t for t in sorted(Afull) if t in Xfull]
    resC = np.array([Afull[t][1] - (s_f * R_f @ Xfull[t][1] + t_f) for t in ts])          # 中心残差(ARKit 世界)
    resR = [Afull[t][0].T @ (R_f @ Xfull[t][0]) for t in ts]                              # 相机系旋转残差
    idx_of = {t: i for i, t in enumerate(ts)}
    rng = np.random.default_rng(11); n = len(ts)
    synth = {'C': [], 'R': [], 'CR': []}
    lags = rng.integers(n // 10, n - n // 10, 60)
    for lag in lags:
        for mode in synth:
            P = {}
            for t, (R, C) in run.ark.items():
                if t not in idx_of: continue
                j = (idx_of[t] - lag) % n
                RR = R @ resR[j] if 'R' in mode else R
                CC = C + resC[j] if 'C' in mode else C
                P[t] = (RR, CC)
            synth[mode].append(summ(eval_curve(run, P)))
    out['synth'] = {m: dict(frac_argmin0=float(np.mean([v['argmin'] == 0 for v in L])),
                            argmin_hist={str(o): int(sum(v['argmin'] == o for v in L)) for o in OFFS},
                            between0_med=float(np.median([v['between0'] for v in L])),
                            between0_p=[float(x) for x in np.percentile([v['between0'] for v in L], [10, 90])],
                            n0_med=float(np.median([v['n0'] for v in L])))
                    for m, L in synth.items()}
    # 时移扫描(插值;ARKit 也插值作为对照)
    IA = Interp(all_arkit(run)); IX = Interp(all_xr(run))
    scan = {}
    for s_ms in (-12, -6, -3, 0, 3, 6, 9, 12, 18):
        for nm, I in (('arkit', IA), ('xr', IX)):
            P = {}
            for t in run.ark:
                p = I(t + int(s_ms * 1e6))
                if p is not None: P[t] = p
            scan[f'{nm}@{s_ms:+d}'] = summ(eval_curve(run, P))
    out['scan'] = scan
    pickle.dump(out, open(f's8_{key}.pkl', 'wb'))
    return out

if __name__ == '__main__':
    import multiprocessing as mp
    with mp.get_context('fork').Pool(3) as p:
        outs = p.map(work, list(RUNS))
    json.dump(outs, open('s8_g4.json', 'w'), indent=1, default=float)
    print('done')
