#!/usr/bin/python3
"""σ = 1 m (upstream prior_position_fallback_stddev) re-analysis of the DEVICE-ALIGN-V1 runs.
Reuses analyze_fix.py helpers unchanged; only the run prefix (fix1m_) and the offline σ (1.0) differ.
  summary : per-run alignment record + delivered/device scale (Umeyama on camera centres)
  heldout : B's pre-fix models, core code fits on even (odd) frames at σ=1, evaluated on the other half
  pairs   : x1.10 positive controls and rerun stability (model-vs-model Sim3 scale)
  live    : live_end (pre-alignment, same run) vs fed device centres -> live/device, delivered/live
"""
import json, os, re, sys
import numpy as np
sys.argv, _argv = sys.argv[:1], sys.argv
import analyze_fix as A  # noqa: E402
sys.argv = _argv
sys.path.insert(0, A.W + '/base_sfmB/tools')
import colmap_bin as CB  # noqa: E402

SIG = 1.0
A.offline.__defaults__ = (SIG,)
RUNS, OUT = A.RUNS, A.OUT
PFX = 'fix1m_'
FEEDS = ['S_prod74_A', 'S_prod74_Xhost', 'S_prod_A', 'S_prod_Xhost', 'S_prod_Xdev', 'S_prod74_A_shuf',
         'S_prod74_Xhost_shuf', 'S_prod74_A_x110', 'S_prod74_Xhost_x110', 'S_deb74_A', 'S_deb74_Xhost',
         'S_deb_A', 'S_deb_Xhost', 'S_deb74_A_x110']
RUNLIST = [(PFX + f, f) for f in FEEDS] + [(PFX + 'S_prod74_A_r2', 'S_prod74_A'), (PFX + 'S_deb_A_r2', 'S_deb_A'),
                                          ('off1m_S_prod74_A', 'S_prod74_A'), ('off1m_S_prod_A', 'S_prod_A'),
                                          ('off1m_S_prod_Xhost', 'S_prod_Xhost')]


def filt(d):
    m = re.search(r'deliver-filter\(get_points\): kept (\d+)/(\d+) \(min_tri_angle=\S+ mirror_ghost=(\d+), isolated_floater=(\d+)',
                  open(d + '/run.log', errors='replace').read())
    return dict(kept=int(m.group(1)), total=int(m.group(2)), mirror_ghost=int(m.group(3)), floater=int(m.group(4))) if m else None


def live_centres(d):
    p = d + '/live/live_end/images.bin'
    if not os.path.exists(p): return None
    out = {}
    for iid, (q, t, nm) in CB.read_images_bin(p).items():
        k = int(''.join(c for c in nm if c.isdigit())); R = A.P.q2R(*q); out[k] = -R.T @ np.asarray(t, float)
    return out


def main(what):
    res = {}
    if what in ('all', 'summary'):
        res['summary'] = []
        for run, fn in RUNLIST:
            d = RUNS + '/' + run
            if not os.path.exists(d + '/delivered_poses.txt'):
                print('missing', run); continue
            r = A.summary_run(run, fn); r['deliver_filter'] = filt(d)
            fd = A.feed(fn); dl = A.delivered(d); ks = sorted(dl)
            D = {k: A.centre(*A.dev_pose_colmap(fd[k])) for k in ks}
            C = {k: A.centre(*dl[k]) for k in ks}
            L = live_centres(d)
            if L:
                kl = sorted(k for k in L if k in D)
                s_ld, _, _ = A.sim3_scale(np.array([D[k] for k in kl]), np.array([L[k] for k in kl]))  # live units / device m
                s_cl, _, _ = A.sim3_scale(np.array([L[k] for k in kl]), np.array([C[k] for k in kl]))  # delivered / live
                r['live_units_per_device_m'] = s_ld; r['delivered_over_live'] = s_cl; r['n_live'] = len(kl)
            res['summary'].append(r)
            a = r['align'] or {}; f = r['deliver_filter'] or {}
            print('%-28s reg=%3d deliv/dev=%.6f live/dev=%s | %-21s inl=%s/%s sim3=%.6f cerr med=%.1f max=%.1fmm rot=%.2f/%.2fdeg | pts=%s kept=%s mg=%s' % (
                run, r['n_reg'], r['deliv_units_per_device_m'], '%.4f' % r['live_units_per_device_m'] if L else '-',
                a.get('status'), a.get('inliers_all'), a.get('n_pairs'), a.get('scale', 0),
                1e3 * a.get('centre_err_m', {}).get('median', 0), 1e3 * a.get('centre_err_m', {}).get('max', 0),
                a.get('rot_err_deg', {}).get('median', 0), a.get('rot_err_deg', {}).get('max', 0),
                f.get('total'), f.get('kept'), f.get('mirror_ghost')))
    if what in ('all', 'heldout'):
        res['heldout'] = []
        B = A.BRUNS
        for rd, fn, tag in [(B + '/diag_S_prod74_A', 'S_prod74_A', 'B_S_prod74_A'), (B + '/diag_S_prod74_Xhost', 'S_prod74_Xhost', 'B_S_prod74_Xhost'),
                            (B + '/diag_S_prod_A', 'S_prod_A', 'B_S_prod_A'), (B + '/diag_S_prod_Xhost', 'S_prod_Xhost', 'B_S_prod_Xhost'),
                            (B + '/diag_S_deb74_A', 'S_deb74_A', 'B_S_deb74_A'), (B + '/diag_S_deb74_Xhost', 'S_deb74_Xhost', 'B_S_deb74_Xhost'),
                            (B + '/diag_S_deb_A', 'S_deb_A', 'B_S_deb_A'), (B + '/diag_S_deb_Xhost', 'S_deb_Xhost', 'B_S_deb_Xhost'),
                            (B + '/S_deb_A', 'S_deb_A', 'B_S_deb_A_rep')]:
            h = A.held_out(rd, fn, tag + '_s1m'); res['heldout'].append(h)
            for k in ('fit_even', 'fit_odd'):
                x = h[k]
                print('%-18s %s n_fit=%3d heldout=%3d scale_err before %+7.2f%% -> after %+6.2f%% | heldout resid med %.1f max %.1f mm (refit floor %.1f) %s' % (
                    tag, k, x['n_fit'], x['heldout_n'], x['heldout_scale_err_before_pct'], x['heldout_scale_err_after_pct'],
                    x['heldout_resid_mm_median'], x['heldout_resid_mm_max'], x['heldout_resid_refit_floor_mm_median'], x['status']))
    if what in ('all', 'pairs'):
        res['pairs'] = {}
        for tag, num, den in [
                ('pos_x110 prod74 A   deliv(x110)/deliv(x1)', 'fix1m_S_prod74_A_x110', 'fix1m_S_prod74_A'),
                ('pos_x110 prod74 X   deliv(x110)/deliv(x1)', 'fix1m_S_prod74_Xhost_x110', 'fix1m_S_prod74_Xhost'),
                ('pos_x110 deb74 A    deliv(x110)/deliv(x1)', 'fix1m_S_deb74_A_x110', 'fix1m_S_deb74_A'),
                ('pos_x110 prod74 A   PRE(x110)/PRE(x1)', 'pre_fix1m_S_prod74_A_x110', 'pre_fix1m_S_prod74_A'),
                ('pos_x110 prod74 X   PRE(x110)/PRE(x1)', 'pre_fix1m_S_prod74_Xhost_x110', 'pre_fix1m_S_prod74_Xhost'),
                ('pos_x110 deb74 A    PRE(x110)/PRE(x1)', 'pre_fix1m_S_deb74_A_x110', 'pre_fix1m_S_deb74_A'),
                ('rerun prod74 A fix r2/r1', 'fix1m_S_prod74_A_r2', 'fix1m_S_prod74_A'),
                ('rerun prod74 A PRE r2/r1', 'pre_fix1m_S_prod74_A_r2', 'pre_fix1m_S_prod74_A'),
                ('rerun deb A    fix r2/r1', 'fix1m_S_deb_A_r2', 'fix1m_S_deb_A'),
                ('rerun deb A    PRE r2/r1', 'pre_fix1m_S_deb_A_r2', 'pre_fix1m_S_deb_A')]:
            n_, d_ = RUNS + '/' + num, RUNS + '/' + den
            if not (os.path.exists(n_ + '/delivered_poses.txt') and os.path.exists(d_ + '/delivered_poses.txt')):
                print('missing', tag); continue
            s, n = A.ratio(n_, d_); res['pairs'][tag] = dict(scale=s, n=n)
            print('%-44s scale=%.6f (%+.3f%%) n=%d' % (tag, s, 100 * (s - 1), n))
    json.dump(res, open(f'{OUT}/analyze_1m_{what}.json', 'w'), indent=1, default=float)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'all')
