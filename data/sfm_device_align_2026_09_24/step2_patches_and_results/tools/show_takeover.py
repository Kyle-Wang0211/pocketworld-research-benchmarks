#!/usr/bin/python3
import json, sys
for p in sys.argv[1:]:
    d = json.load(open(p)); print('==', d['subset'])
    for lab, v in d.items():
        if isinstance(v, dict) and 'cloud' in v:
            pr = v['prior_vs_arkit']['metres_per_arkit_metre']; li = (v.get('live_end_vs_arkit') or {}).get('units_per_arkit_metre')
            de = v['delivered_vs_arkit']['units_per_arkit_metre']; c = v['cloud']; s = v['delivered_vs_clean_colmap']
            print('%-10s %-30s live/dev=%s deliv/dev=%.6f | shape rmse=%.4fmm rot=%.3f/%.3f | cloud n=%5d ->ref med=%.4fmm p90=%.3f >2cm=%.3f%%' % (
                lab, v['run_dir'][5:], '%.4f' % (li / pr) if li else '  -   ', de / pr, s['rmse_mm'], s['rot_err_deg_median'], s['rot_err_deg_max'],
                c['n_points'], c['to_reference_nn']['median_mm'], c['to_reference_nn']['p90_mm'], 100 * c['to_reference_nn']['frac_gt_2cm']))
    for lab, v in d.items():
        if isinstance(v, dict) and 'n_common_registered' in v:
            print('   %-14s X/A units=%.6f  X->A NN med=%.2e mm >1cm=%.3f%% | A->X >1cm=%.3f%%' % (
                lab, v['delivered_X_units_over_A_units'], v['X_to_A_nn']['median_mm'], 100 * v['X_to_A_nn']['frac_gt_1cm'], 100 * v['A_to_X_nn(holes in X)']['frac_gt_1cm']))
