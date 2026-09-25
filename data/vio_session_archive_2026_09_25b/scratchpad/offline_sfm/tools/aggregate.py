#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 2026-09-25] 汇总:场 × 臂,外加核自身不确定性与臂间配对差。

用法:aggregate.py <run_glob_prefix>(默认 runs/ 下所有 <scene>_p<ph>_<arm>_r<rep>)[--tag 名]
核不确定性 = 同一(场, 相位, 臂)重复运行之间的差异(同一输入、只有核的运行间抖动);
臂间差 = 同一(场, 相位)里各臂重复均值之差(配对:照片完全相同)。
"""
import glob, json, os, re, sys
import numpy as np

O = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm'
sys.path.insert(0, O + '/tools')
import analyze_run as AR  # noqa: E402

BASE = 'F'
ARMS = ['A', 'AN', 'F', 'B1', 'B2', 'X2', 'X1', 'FN', 'XN', 'BN', 'F16', 'X16', 'B16', 'F21', 'X21', 'B21']
ARM_CN = {'A': 'ARKit', 'F': 'XRSLAM 前端', 'B1': '后端首次', 'B2': '后端定稿', 'X2': '定稿+外推', 'X1': '首次+外推', 'FN': '新前端', 'XN': '新定稿+外推', 'BN': '新后端定稿', 'AN': 'ARKit', 'F16': '前端(前移16)', 'X16': '定稿+外推(前移16)', 'B16': '后端定稿(前移16)', 'F21': '前端(前移21)', 'X21': '定稿+外推(前移21)', 'B21': '后端定稿(前移21)'}


def main():
    pat = sys.argv[1] if len(sys.argv) > 1 else 'runs/*_p?_*_r*'
    tag = sys.argv[2] if len(sys.argv) > 2 else 'main'
    only = set(sys.argv[3].split(',')) if len(sys.argv) > 3 else None  # [新引擎轮] 只统计这些臂
    rows = []
    for d in sorted(glob.glob(f'{O}/{pat}')):
        if not re.search(r'/\w{4}_[pqe]\d_(A|F|B1|B2|X1|X2|FN|XN|BN|AN|F16|X16|B16|F21|X21|B21)_r\d+$', d):
            continue
        if not os.path.exists(d + '/run.log'):
            continue
        if only and d.rsplit('_r', 1)[0].rsplit('_', 1)[1] not in only:
            continue
        rows.append(AR.analyze(d))
    bad = [r['run'] for r in rows if 'error' in r]
    rows = [r for r in rows if 'error' not in r]
    json.dump(rows, open(f'{O}/summary_{tag}_runs.json', 'w'), indent=1, ensure_ascii=False)
    scenes = sorted({r['scene'] for r in rows})
    global BASE
    BASE = os.environ.get('AGG_BASE') or ('F' if any(r['arm'] == 'F' for r in rows) else 'FN')  # 配对基准:有旧前端用旧前端,否则用新前端
    cell = {}
    for r in rows:
        cell.setdefault((r['scene'], r['phase'], r['arm']), []).append(r)

    def vals(rs, f):
        return np.array([f(r) for r in rs], dtype=float)

    metrics = {
        'reg_frac': lambda r: r['n_reg'] / r['n_photos'],
        'n_reg': lambda r: r['n_reg'],
        'n_photos': lambda r: r['n_photos'],
        'rms_mm': lambda r: 1e3 * r['centre_err_rms_m'],
        'max_mm': lambda r: 1e3 * r['align']['centre_err_max_m'],
        'med_mm': lambda r: 1e3 * r['align']['centre_err_median_m'],
        'k_pct': lambda r: r['vs_arkit']['k_pct'],
        'kL_pct': lambda r: r['vs_lidar_chained']['k_pct'],
        'ate_cm': lambda r: r['vs_arkit']['ate_cm'],
        'kin_pct': lambda r: r['input_vs_arkit']['k_pct'],
        'kx_pct': lambda r: r['vs_arkit_excl_core_outliers']['k_pct'],
        'kxL_pct': lambda r: r['vs_arkit_excl_core_outliers']['kL_pct'],
        'atex_cm': lambda r: r['vs_arkit_excl_core_outliers']['ate_cm'],
        'reproj': lambda r: r['reproj_px_mean'],
        'npts': lambda r: r['n_points'],
        'gate_ok': lambda r: 1.0 if r['align']['status'] == 'aligned' else 0.0,
    }
    out = {'n_runs': len(rows), 'failed_runs': bad, 'scenes': {}}
    for s in scenes:
        so = {}
        phases = sorted({p for (sc, p, a) in cell if sc == s})
        for a in ARMS:
            rs = [r for (sc, p, aa), v in cell.items() if sc == s and aa == a for r in v]
            if not rs:
                continue
            ao = {'n_runs': len(rs)}
            for mk, f in metrics.items():
                v = vals(rs, f)
                ao[mk] = {'mean': float(v.mean()), 'median': float(np.median(v)), 'min': float(v.min()), 'max': float(v.max())}
            # 核自身不确定性:各相位内重复间 SD 与极差,取相位平均
            sds, rngs, ident = {}, {}, []
            for mk in ('k_pct', 'kL_pct', 'rms_mm', 'max_mm', 'ate_cm', 'n_reg', 'reproj'):
                sd_l, rg_l = [], []
                for p in phases:
                    v = vals(cell.get((s, p, a), []), metrics[mk])
                    if v.size >= 2:
                        sd_l.append(v.std(ddof=1)); rg_l.append(v.max() - v.min())
                sds[mk] = float(np.mean(sd_l)) if sd_l else None
                rngs[mk] = float(np.max(rg_l)) if rg_l else None
            for p in phases:
                hs = {r['sha_delivered_poses'] for r in cell.get((s, p, a), [])}
                ident.append(len(hs))
            ao['core_rep_sd'] = sds
            ao['core_rep_range_max'] = rngs
            ao['distinct_delivered_sha_per_phase'] = ident
            ao['align_status_counts'] = {st: sum(1 for r in rs if r['align']['status'] == st)
                                         for st in sorted({r['align']['status'] for r in rs})}
            ao['per_phase_mean'] = {int(p): {mk: float(vals(cell[(s, p, a)], metrics[mk]).mean())
                                             for mk in ('k_pct', 'kL_pct', 'rms_mm', 'max_mm', 'ate_cm', 'n_reg')}
                                    for p in phases if (s, p, a) in cell}
            so[a] = ao
        # 配对差:相对 F(前端)
        diffs = {}
        for a in [x for x in ('B1', 'B2', 'X2', 'X1', 'FN', 'XN', 'BN', 'A', 'AN', 'F16', 'X16', 'B16', 'F21', 'X21', 'B21') if x != BASE and any(k[0] == s and k[2] == x for k in cell)]:
            dd = {}
            for mk in ('k_pct', 'kL_pct', 'rms_mm', 'max_mm', 'ate_cm', 'n_reg', 'reproj'):
                d_p, se_p = [], []
                for p in phases:
                    va = vals(cell.get((s, p, a), []), metrics[mk]); vf = vals(cell.get((s, p, BASE), []), metrics[mk])
                    if va.size and vf.size:
                        d_p.append(va.mean() - vf.mean())
                        se_p.append(np.sqrt((va.var(ddof=1) / va.size if va.size > 1 else 0) +
                                            (vf.var(ddof=1) / vf.size if vf.size > 1 else 0)))
                d_p = np.array(d_p); se_p = np.array(se_p)
                dd[mk] = {'per_phase': [float(x) for x in d_p], 'mean': float(d_p.mean()),
                          'core_se_per_phase': [float(x) for x in se_p],
                          'z_per_phase': [float(x / y) if y > 0 else None for x, y in zip(d_p, se_p)]}
            diffs[f'{a}_minus_F'] = dd
        so['paired_diff'] = diffs
        out['scenes'][s] = so
    json.dump(out, open(f'{O}/summary_{tag}.json', 'w'), indent=1, ensure_ascii=False)
    # 打印中文表
    print(f'运行数 {len(rows)},失败 {bad}')
    hdr = '| 场 | 臂 | 注册 均/总(极值) | 闸通过 | Sim3 残差 RMS mm 中位(极值) | 残差最大 mm 中位(最大) | 交付 k 对 ARKit 中位(极值) | 链到 LiDAR 中位 | ATE 对 ARKit cm 中位(最大) | 喂入位姿 k 对 ARKit | 重投影 px | 点数 |'
    print(hdr); print('|' + '---|' * 12)
    for s in scenes:
        for a in ARMS:
            if a not in out['scenes'][s]:
                continue
            ao = out['scenes'][s][a]
            g = lambda mk: ao[mk]['mean']
            md = lambda mk: ao[mk]['median']
            print(f"| {s} | {ARM_CN[a]} | {g('n_reg'):.1f}/{g('n_photos'):.1f} ({ao['n_reg']['min']:.0f}–{ao['n_reg']['max']:.0f}) | "
                  f"{int(round(g('gate_ok')*ao['n_runs']))}/{ao['n_runs']} | "
                  f"{md('rms_mm'):.1f} ({ao['rms_mm']['min']:.1f}–{ao['rms_mm']['max']:.1f}) | {md('max_mm'):.1f} ({ao['max_mm']['max']:.0f}) | "
                  f"{md('k_pct'):+.2f}% ({ao['k_pct']['min']:+.2f}…{ao['k_pct']['max']:+.2f}) | {md('kL_pct'):+.2f}% | "
                  f"{md('ate_cm'):.2f} ({ao['ate_cm']['max']:.2f}) | {md('kin_pct'):+.2f}% | {md('reproj'):.3f} | {md('npts'):.0f} |")
    print()
    print('并列口径(剔除核自己闸判的离群帧后):')
    for s in scenes:
        for a in ARMS:
            if a not in out['scenes'][s]:
                continue
            ao = out['scenes'][s][a]
            print(f"  {s} {ARM_CN[a]}: k 对 ARKit 中位 {ao['kx_pct']['median']:+.2f}% (极值 {ao['kx_pct']['min']:+.2f}…{ao['kx_pct']['max']:+.2f}) "
                  f"链到 LiDAR 中位 {ao['kxL_pct']['median']:+.2f}% 均值 {ao['kxL_pct']['mean']:+.2f}% ATE 中位 {ao['atex_cm']['median']:.2f} cm (最大 {ao['atex_cm']['max']:.2f})")
    print()
    print('核自身不确定性(同相位同臂重复间 SD,相位平均;括号为最大极差):')
    for s in scenes:
        for a in ARMS:
            if a not in out['scenes'][s]:
                continue
            c = out['scenes'][s][a]
            print(f"  {s} {ARM_CN[a]}: k SD {c['core_rep_sd']['k_pct']:.3f}pp (极差 {c['core_rep_range_max']['k_pct']:.3f}) "
                  f"RMS SD {c['core_rep_sd']['rms_mm']:.2f} mm (极差 {c['core_rep_range_max']['rms_mm']:.2f}) "
                  f"ATE SD {c['core_rep_sd']['ate_cm']:.3f} cm 注册数 SD {c['core_rep_sd']['n_reg']:.2f} "
                  f"每相位不同交付 sha 数 {c['distinct_delivered_sha_per_phase']} 闸 {c['align_status_counts']}")
    print()
    print('配对差(同一组照片,减去 XRSLAM 前端;每相位的差 / 核标准误 z):')
    for s in scenes:
        for a in [x for x in ('B1', 'B2', 'X2', 'X1', 'FN', 'XN', 'BN', 'A', 'AN', 'F16', 'X16', 'B16', 'F21', 'X21', 'B21') if f'{x}_minus_F' in out['scenes'][s]['paired_diff']]:
            d = out['scenes'][s]['paired_diff'][f'{a}_minus_F']
            def fmt(mk, unit):
                x = d[mk]
                zs = ','.join(f'{z:+.1f}' if z is not None else 'na' for z in x['z_per_phase'])
                return f"{mk} {x['mean']:+.3f}{unit} [各相位 {','.join(f'{v:+.3f}' for v in x['per_phase'])}; z {zs}]"
            print(f"  {s} {ARM_CN[a]}−前端: {fmt('k_pct','pp')} | {fmt('rms_mm','mm')} | {fmt('ate_cm','cm')} | {fmt('n_reg','')}")


    # ── 跨格配对(每格 = 同一场同一相位同一组照片;格内取重复的中位数)──
    from math import comb
    def sign_p(n_better, n):  # 双侧符号检验
        k = min(n_better, n - n_better)
        return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)
    cells = sorted({(sc, p) for (sc, p, a) in cell})
    glob_out = {}
    print()
    print('跨格配对(每格取重复中位数;「更好」= 残差/ATE 更小、|k_L| 更小、注册更多):')
    for a in [x for x in ('B1', 'B2', 'X2', 'X1', 'FN', 'XN', 'BN', 'A', 'AN', 'F16', 'X16', 'B16', 'F21', 'X21', 'B21') if x != BASE and any(k[2] == x for k in cell)]:
        go = {}
        for mk, better in (('rms_mm', 'lower'), ('max_mm', 'lower'), ('ate_cm', 'lower'), ('kL_abs', 'lower'),
                           ('n_reg', 'higher'), ('gate_trip', 'lower')):
            f = (lambda r: abs(metrics['kL_pct'](r))) if mk == 'kL_abs' else \
                (lambda r: 1.0 - metrics['gate_ok'](r)) if mk == 'gate_trip' else metrics[mk]
            d, spread = [], []
            for c in cells:
                va = vals(cell.get((c[0], c[1], a), []), f); vf = vals(cell.get((c[0], c[1], BASE), []), f)
                if not (va.size and vf.size):
                    continue
                agg = np.mean if mk == 'gate_trip' else np.median
                d.append(agg(va) - agg(vf))
                spread.append(max(va.max() - va.min(), vf.max() - vf.min()))
            d = np.array(d)
            nb = int(((d < 0) if better == 'lower' else (d > 0)).sum()); nw = int(((d > 0) if better == 'lower' else (d < 0)).sum())
            go[mk] = {'diff_per_cell': [float(x) for x in d], 'n_better': nb, 'n_worse': nw, 'n_tie': int(len(d) - nb - nw),
                      'median_diff': float(np.median(d)), 'mean_diff': float(d.mean()),
                      'median_within_cell_rep_range': float(np.median(spread)),
                      'sign_test_p': sign_p(nb, nb + nw) if nb + nw else None}
            print(f"  {ARM_CN[a]}−前端 {mk}: 更好 {nb} / 更差 {nw} / 持平 {len(d)-nb-nw} 格,差中位 {np.median(d):+.3f} 均值 {d.mean():+.3f};"
                  f"格内重复极差中位 {np.median(spread):.3f};符号检验 p={go[mk]['sign_test_p'] if go[mk]['sign_test_p'] is None else round(go[mk]['sign_test_p'],3)}")
        glob_out[f'{a}_minus_F'] = go
    out['cross_cell'] = glob_out
    json.dump(out, open(f'{O}/summary_{tag}.json', 'w'), indent=1, ensure_ascii=False)


if __name__ == '__main__':
    main()
