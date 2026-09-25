import json, sys, numpy as np
o = json.load(open(sys.argv[1]))
pairs = o['pairs']
keys = sorted({k for p in pairs for k in p['res']})
w = np.array([p['w'] for p in pairs]); expo = [p['exp'] for p in pairs]
print('scene', o['scene'], 'pairs', len(pairs), '|w| rad/s quartiles', np.round(np.nanpercentile(w, [25, 50, 75, 95]), 3))
bins = [0, 0.3, 0.6, 1.0, 10]
print('%-22s %6s %8s %8s %8s %8s | surv(FB) by |w| bins %s' % ('arm', 'npts', 'epiARK', 'epiSelf', 'epi_p90', 'fb640', bins))
for k in keys:
    samp, sself, fb, n, okfb = [], [], [], [], []
    surv_bins = {b: [0, 0] for b in range(len(bins) - 1)}
    for p in pairs:
        r = p['res'].get(k, {}).get('cv_flip')
        if not r: continue
        samp += r['samp640']; sself += r.get('sself640', []); fb += r['fb640']; n.append(r['n']); okfb.append(r['okfb'])
        b = np.searchsorted(bins, p['w']) - 1
        if 0 <= b < len(bins) - 1:
            surv_bins[b][0] += r['okfb']; surv_bins[b][1] += r['n']
    samp, sself, fb = map(np.array, (samp, sself, fb))
    sv = ' '.join('%.3f' % (a / b) if b else '  -  ' for a, b in surv_bins.values())
    print('%-22s %6.0f %8.4f %8.4f %8.4f %8.4f | %s' % (k, np.mean(n), np.median(samp), np.median(sself) if len(sself) else np.nan,
          np.percentile(samp, 90), np.median(fb), sv))
ch = o.get('chains', [])
if ch:
    print('chains (common 640 points, survival after 10/20/30 frames; epipolar residual frame0->j px640 median):')
    ks = [k for k in ch[0] if k.endswith('_off') or k.endswith('_scl')]
    for k in ks:
        s = np.array([c[k] for c in ch if k in c])
        e = {j: np.concatenate([np.array(c[k + '_epi'].get(str(j), c[k + '_epi'].get(j, []))) for c in ch]) for j in (10, 20, 30)}
        print('  %-10s surv %s  epi %s' % (k, np.round(s.mean(0)[[9, 19, 29]], 3), [round(float(np.median(e[j])), 3) if len(e[j]) else None for j in (10, 20, 30)]))
if ch:
    # drift on the SAME survivors: points alive at frame 30 in every arm compared (removes survivor selection)
    arms = [k for k in ch[0] if (k.endswith('_off') or k.endswith('_scl'))]
    print('chains, drift on common survivors (alive at 30 in all arms): epipolar frame0->30 px640 median / p90, n')
    acc = {a: [] for a in arms}; ntot = 0
    for c in ch:
        sets = [set(c[a + '_alive_idx']) for a in arms if a + '_alive_idx' in c]
        if len(sets) != len(arms): continue
        common = set.intersection(*sets); ntot += len(common)
        for a in arms:
            idx = c[a + '_alive_idx']; e = c[a + '_epi'].get('30', c[a + '_epi'].get(30, []))
            if len(e) != len(idx): continue
            m = {i: v for i, v in zip(idx, e)}
            acc[a] += [m[i] for i in common]
    for a in arms:
        v = np.array(acc[a]); print('  %-10s %.3f / %.3f  n=%d' % (a, np.median(v), np.percentile(v, 90), len(v)) if len(v) else a)
