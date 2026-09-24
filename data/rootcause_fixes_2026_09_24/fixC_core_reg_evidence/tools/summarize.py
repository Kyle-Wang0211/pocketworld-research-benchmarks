#!/usr/bin/python3
"""Collect runs/*/metrics.json into results/summary.json + a markdown table."""
import json, os, glob, re
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = []
for mf in sorted(glob.glob(W + '/runs/*/metrics.json')):
    if '/stale_' in mf: continue
    m = json.load(open(mf)); run = m['run']
    tok = run.split('_')
    if tok[0] in ('j', 'r', 'p'): arm = tok[1]; subj = '_'.join(tok[2:]) + {'j': ' JPEG', 'r': ' RESUME', 'p': ' PHONEFEAT'}[tok[0]]
    else: arm = tok[0]; subj = '_'.join(tok[1:])
    res = m.get('result') or {}; da = m.get('device_align') or {}; rev = m.get('reg_evidence') or {}
    rv = m.get('relpose_vs_reference') or m.get('relpose_vs_twoview') or {}
    cl = m.get('cloud_to_reference') or {}; cam = m.get('cameras_vs_reference') or {}
    ls = m.get('live_stages') or {}
    row = dict(subject=subj, arm=arm, n_reg=m['n_reg'], n_fed=m['n_fed'], unreg=m['unregistered_fids'],
               points=res.get('n_points'), reproj=res.get('mean_reproj_px'), gate=da.get('status'),
               gate_inliers='%s/%s' % (da.get('inliers'), da.get('pairs')), scale=da.get('scale'),
               misplaced=sorted(int(k) for k in m['centre_err_mm']['misplaced_gt112']), cerr_med=round(m['centre_err_mm']['median'], 1),
               cerr_max=round(m['centre_err_mm']['max'], 1), rel_bad=rv.get('n_dir_gt20'), rel_rot_bad=rv.get('n_rot_gt5'), rel_n=rv.get('n_pairs'),
               rel_bad_list=rv.get('bad'), cloud_med=cl.get('median_mm'), cloud_gt2=cl.get('frac_gt_2cm'), cam_rmse=cam.get('rmse_mm'),
               units_per_arkit_m=m.get('delivered_units_per_arkit_m'), stream_s=float(res.get('stream_ms', 0)) / 1e3,
               fin_s=float(res.get('finalize_ms', 0)) / 1e3, rss=m.get('max_rss_MB'), ev=rev,
               live_end_misplaced=sorted(int(k) for k in (ls.get('live_end') or {}).get('misplaced_gt112', {})),
               live_pre_misplaced=sorted(int(k) for k in (ls.get('live_end_pre_resume') or {}).get('misplaced_gt112', {})),
               untrusted_reg=m.get('untrusted_registered'), untrusted_unreg=m.get('untrusted_unregistered'),
               untrusted_self=m.get('untrusted_self_sim3'), untrusted_via_trusted=m.get('untrusted_via_trusted_fit_mm'))
    rows.append(row)
json.dump(rows, open(W + '/results/summary.json', 'w'), indent=1, default=float)
order = {'base': 0, 'a': 1, 'b': 2, 'u06v2': 3, 'u06av2': 4, 'u06bv2': 5, 'uB2': 6, 'uB2a': 7, 'uB2b': 8, 'u0': 9, 'u0a': 10, 'u0b': 11, 'u03': 12, 'u03a': 13, 'u03b': 14, 'u06v3': 15}
for r in sorted(rows, key=lambda r: (r['subject'], order.get(r['arm'], 9), r['arm'])):
    print('| %s | %s | %d/%d %s | %s | %s | %s %s | %s | %s | %.1f/%.1f | %s/%s | %s | %s | %s | %.0f+%.1f |' % (
        r['subject'], r['arm'], r['n_reg'], r['n_fed'], r['unreg'] if r['unreg'] else '', r['points'], r['reproj'], r['gate'], r['gate_inliers'],
        r['scale'][:6] if r['scale'] else '-', r['misplaced'] or '-', r['cerr_med'], r['cerr_max'], r['rel_bad'], r['rel_n'],
        ('%.1f/%.3f' % (r['cloud_med'], r['cloud_gt2'])) if r['cloud_med'] is not None else '-',
        ('%.4f' % r['units_per_arkit_m']) if r['units_per_arkit_m'] else '-', r['live_end_misplaced'] or '-', r['stream_s'], r['fin_s']))
