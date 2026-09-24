#!/usr/bin/python3
"""σ = 0.040 m via the upstream per-prior covariance path (device_pose_alignment_v1.h [C2]) — Task A analysis.
Reuses analyze_1m.py / analyze_fix.py helpers unchanged; only the run prefix (cov_) and offline σ (0.040) differ."""
import json, os, sys
import numpy as np
sys.argv, _argv = sys.argv[:1], sys.argv
import analyze_1m as M  # noqa: E402
A = M.A
sys.argv = _argv
A.offline.__defaults__ = (0.040,)
RUNS, OUT = A.RUNS, A.OUT
FEEDS = ['S_prod74_A', 'S_prod74_Xhost', 'S_prod_A', 'S_prod_Xhost', 'S_prod_Xdev', 'S_prod74_A_shuf', 'S_prod74_Xhost_shuf',
         'S_prod74_A_x110', 'S_prod74_Xhost_x110', 'S_deb74_A', 'S_deb74_Xhost', 'S_deb_A', 'S_deb_Xhost', 'S_deb74_A_x110']
res = {'summary': [], 'pairs': {}, 'heldout': []}
for f in FEEDS + ['S_prod74_A_r2']:
    run = 'cov_' + f; fn = f.replace('_r2', ''); d = RUNS + '/' + run
    if not os.path.exists(d + '/delivered_poses.txt'): continue
    r = A.summary_run(run, fn); r['deliver_filter'] = M.filt(d); res['summary'].append(r); a = r['align'] or {}
    print('%-26s reg=%3d deliv/dev=%.6f | %-21s inl=%s/%s sim3=%.6f max_err=%.1fmm cerr med=%.1f max=%.1fmm | pts=%s' % (
        run, r['n_reg'], r['deliv_units_per_device_m'], a.get('status'), a.get('inliers_all'), a.get('n_pairs'), a.get('scale', 0),
        1e3 * a.get('max_error_m', 0), 1e3 * a.get('centre_err_m', {}).get('median', 0), 1e3 * a.get('centre_err_m', {}).get('max', 0),
        (r['deliver_filter'] or {}).get('kept')))
for tag, num, den in [('x110 prod74 A  deliv(x110)/deliv(x1)', 'cov_S_prod74_A_x110', 'cov_S_prod74_A'),
                      ('x110 prod74 X  deliv(x110)/deliv(x1)', 'cov_S_prod74_Xhost_x110', 'cov_S_prod74_Xhost'),
                      ('x110 deb74 A   deliv(x110)/deliv(x1)', 'cov_S_deb74_A_x110', 'cov_S_deb74_A'),
                      ('rerun prod74 A cov r2/r1', 'cov_S_prod74_A_r2', 'cov_S_prod74_A'),
                      ('cov vs sigma1m prod74 A', 'cov_S_prod74_A', 'fix1m_S_prod74_A'),
                      ('cov vs sigma1m prod_A', 'cov_S_prod_A', 'fix1m_S_prod_A'),
                      ('cov vs sigma1m deb74_A', 'cov_S_deb74_A', 'fix1m_S_deb74_A')]:
    n_, d_ = RUNS + '/' + num, RUNS + '/' + den
    if not (os.path.exists(n_ + '/delivered_poses.txt') and os.path.exists(d_ + '/delivered_poses.txt')): print('missing', tag); continue
    s, n = A.ratio(n_, d_); res['pairs'][tag] = dict(scale=s, n=n); print('%-40s scale=%.6f (%+.3f%%) n=%d' % (tag, s, 100 * (s - 1), n))
B = A.BRUNS
for rd, fn, tag in [(B + '/diag_S_prod74_A', 'S_prod74_A', 'B_S_prod74_A'), (B + '/diag_S_prod74_Xhost', 'S_prod74_Xhost', 'B_S_prod74_Xhost'),
                    (B + '/diag_S_prod_A', 'S_prod_A', 'B_S_prod_A'), (B + '/diag_S_prod_Xhost', 'S_prod_Xhost', 'B_S_prod_Xhost'),
                    (B + '/diag_S_deb74_A', 'S_deb74_A', 'B_S_deb74_A'), (B + '/diag_S_deb74_Xhost', 'S_deb74_Xhost', 'B_S_deb74_Xhost'),
                    (B + '/diag_S_deb_A', 'S_deb_A', 'B_S_deb_A'), (B + '/diag_S_deb_Xhost', 'S_deb_Xhost', 'B_S_deb_Xhost'),
                    (B + '/S_deb_A', 'S_deb_A', 'B_S_deb_A_rep')]:
    h = A.held_out(rd, fn, tag + '_cov040'); res['heldout'].append(h)
    for k in ('fit_even', 'fit_odd'):
        x = h[k]
        print('%-18s %s n_fit=%3d heldout=%3d scale_err before %+7.2f%% -> after %+6.2f%% | resid med %.1f max %.1f mm %s' % (
            tag, k, x['n_fit'], x['heldout_n'], x['heldout_scale_err_before_pct'], x['heldout_scale_err_after_pct'],
            x['heldout_resid_mm_median'], x['heldout_resid_mm_max'], x['status']))
json.dump(res, open(f'{OUT}/analyze_cov040.json', 'w'), indent=1, default=float)
