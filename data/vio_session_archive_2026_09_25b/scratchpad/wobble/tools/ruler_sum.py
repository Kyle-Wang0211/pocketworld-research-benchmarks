import json, sys, numpy as np
W='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble'
out = {}
for sc in ['fb5d','13f5','6d18','7353']:
    J = json.load(open(f'{W}/stats/ruler_{sc}/lidar_ruler_report.json'))
    T = J['trajectories']
    t0 = min(p['t_a'] for p in T['arkit']['pairs'] if 'scale_to_metric' in p)
    print('== %s' % sc)
    for n in ['arkit','api','latest','kf']:
        tr = T[n]; e = tr['estimate']
        ok = [p for p in tr['pairs'] if 'scale_to_metric' in p]
        t = np.array([p['t_a'] - t0 for p in ok]); k = 1/np.array([p['scale_to_metric'] for p in ok])
        seg = []
        for a in np.arange(0, 30, 5.0):
            m = (t >= a) & (t < a + 5)
            if m.sum() >= 3: seg.append((a, float(np.median(k[m])), int(m.sum())))
        sv = np.array([s[1] for s in seg])
        rel = sv / e['k']
        g = e.get('gates', {})
        nf = tr.get('noise_floor', {}) or {}
        print('  %-6s k %.4f (%+.2f%%)  有效对 %2d/%d  帧对间IQR %.3f  闸 G1%s G2%s G3%s G4%s → %s | 5s段(对LiDAR) %s | 段/全场 min %+.1f%% max %+.1f%% sd %.1f%% | 四分段 %s%s' % (
            n, e['k'], 100*(e['k']-1), e['pairs_with_scale'], e['pairs_attempted'], e.get('between_pair_rel_iqr', np.nan),
            *['✓' if g.get(x) else '✗' for x in ['G1_pairs','G2_between_rel_iqr','G3_within_rel_iqr','G4_alignment_minimum_at_0']],
            tr['verdict'], ' '.join('%.3f(%d)' % (s[1], s[2]) for s in seg), 100*(rel.min()-1), 100*(rel.max()-1), 100*rel.std(),
            ' '.join('%.3f' % x for x in (tr.get('segments_k') or [])),
            ('  噪声底 %s' % np.round(nf['k_95_noise_floor'], 4)) if 'k_95_noise_floor' in nf else ''))
        out[f'{sc}:{n}'] = dict(k=e['k'], seg5=seg, verdict=tr['verdict'], gates=g, quarters=tr.get('segments_k'))
    for c in J['cross_check_vs_canonical_sim3']:
        if c['ref'] == 'arkit': print('   交叉核对 %s/arkit:尺子比值 %.4f vs Sim3 %.4f 差 %+.2f%%' % (c['est'], c['k_ratio_from_ruler'], c['k_sim3_canonical'], c['diff_pct']))
json.dump(out, open(f'{W}/stats/ruler_summary.json','w'), indent=1, default=float)
