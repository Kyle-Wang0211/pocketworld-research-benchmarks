import sys, json, pickle, numpy as np
from g4lib import *
from s8_g4 import eval_curve, summ, boot_argmin, aligned_xr, OFFS

def work(key):
    run = Run(key); out = {'key': key}
    # ① G4 阴性对照:把「真」深度换成 +1 行(错位 100 ms),曲线的偏移相对它来算 ⇒ 最小值应在 -1
    for bad in (+1, -1):
        cr = {o: ratios_of(run.measure(run.ark, depths=[run.scene.depth_of(fa, offset_rows=o + bad) for fa, _, _, _ in run.matched])) for o in OFFS}
        s = summ(cr); s['boot_iid'] = boot_argmin(cr, B=1000)
        out[f'nc_misaligned_{bad:+d}'] = s
    # ② 功效曲线:ARKit + α·(XR 残差 C+R,循环平移)
    Afull = all_arkit(run); Xfull = all_xr(run)
    s_f, R_f, t_f, _ = sim3_align(Xfull, Afull)
    ts = [t for t in sorted(Afull) if t in Xfull]
    resC = np.array([Afull[t][1] - (s_f * R_f @ Xfull[t][1] + t_f) for t in ts])
    resR = [rot_log(Afull[t][0].T @ (R_f @ Xfull[t][0])) for t in ts]
    idx_of = {t: i for i, t in enumerate(ts)}; n = len(ts)
    rng = np.random.default_rng(5); lags = rng.integers(n // 10, n - n // 10, 40)
    pw = {}
    for alpha in (0.0, 0.25, 0.5, 0.75, 1.0):
        L = []
        for lag in (lags if alpha > 0 else lags[:1]):
            P = {}
            for t, (R, C) in run.ark.items():
                if t not in idx_of: continue
                j = (idx_of[t] - lag) % n
                P[t] = (R @ rot_exp(alpha * resR[j]), C + alpha * resC[j])
            L.append(summ(eval_curve(run, P)))
        pw[str(alpha)] = dict(frac0=float(np.mean([v['argmin'] == 0 for v in L])),
                              between0_med=float(np.median([v['between0'] for v in L])),
                              pairs=[(v['between0'], v['argmin'] == 0) for v in L])
    out['power'] = pw
    # ③ 纯轨迹逐对基线比(XR 按整段 Sim3 尺度)与混合轨迹分段 k
    s_sub, _, _, _ = sim3_align(run.xr, run.ark)
    br = []
    for fa, fb, _, _ in run.matched:
        ca, cb = run.ark[fa['t_ns']][1], run.ark[fb['t_ns']][1]
        xa, xb = run.xr[fa['t_ns']][1], run.xr[fb['t_ns']][1]
        da = np.linalg.norm(cb - ca)
        if da > 0.02: br.append(s_sub * np.linalg.norm(xb - xa) / da)
    br = np.array(br); q1, q3 = np.percentile(br, [25, 75])
    out['baseline_ratio'] = dict(n=len(br), med=float(np.median(br)), rel_iqr=float((q3 - q1) / np.median(br)))
    xa_, _ = aligned_xr(run)
    common = [t for t in run.ark if t in xa_]
    hyb = {t: (run.ark[t][0], xa_[t][1]) for t in common}
    out['segments'] = {nm: LR.segments(run.measure(P)) for nm, P in (('arkit', run.ark), ('xr', run.xr), ('arkRot_xrC', hyb))}
    pickle.dump(out, open(f's11_{key}.pkl', 'wb'))
    return out

if __name__ == '__main__':
    import multiprocessing as mp
    with mp.get_context('fork').Pool(3) as p:
        outs = p.map(work, list(RUNS))
    json.dump(outs, open('s11.json', 'w'), indent=1, default=float)
    for o in outs:
        print('=====', o['key'])
        for bad in ('+1', '-1'):
            s = o[f'nc_misaligned_{bad}']
            print(f"  G4 阴性对照(深度整体错 {bad} 行)ARKit:argmin={s['argmin']}  曲线 " + ' '.join(f"{k}:{v:.3f}" for k, v in s['curve'].items()) + f"  bootstrap {s['boot_iid']}")
        print('  功效曲线(ARKit + α·XR 残差):' + '  '.join(f"α={a}: P(argmin=0)={v['frac0']:.2f}, 帧对间IQR中位 {v['between0_med']:.3f}" for a, v in o['power'].items()))
        b = o['baseline_ratio']; print(f"  纯轨迹逐对基线比 XR/ARKit(0.33 s 帧对,整段 Sim3 尺度后):n={b['n']} 中位 {b['med']:.4f} 相对 IQR {b['rel_iqr']:.3f}")
        print('  分段 k:' + '  '.join(f"{k}: {np.round(v, 4).tolist() if v else v}" for k, v in o['segments'].items()))
