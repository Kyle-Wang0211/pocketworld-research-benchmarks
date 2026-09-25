#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三种位姿(api/latest/kf,TUM 由 make_tums.py 生成,只取 XR 收下的帧)对 ARKit:全场 k、ATE、5 s 分段(不重叠)与 5 s 滑窗(步 1 s)。"""
import json, sys
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob

def load_tum(fn, keep=None):
    tns, P, Q = [], [], []
    for l in open(fn):
        f = l.split()
        if not f: continue
        s, fr = f[0].split('.')
        t = int(s) * 10**9 + int(fr)
        if keep is not None and t not in keep: continue
        tns.append(t); P.append([float(x) for x in f[1:4]]); Q.append([float(x) for x in f[4:8]])
    return dict(tns=np.array(tns, dtype=np.int64), P=np.array(P), Q=np.array(Q))

def seg_stats(J, kg, win, step):
    t, X, Y = J['t'], J['X'], J['Y']
    out = []; a = t[0]
    while a + win <= t[-1] + 1e-6:
        m = (t >= a) & (t < a + win)
        if m.sum() >= 30: out.append((a - t[0], 1 / wob.umeyama(X[:, m], Y[:, m])[0] / kg - 1))
        a += step
    return out

res = {}
for sc, tag in [('fb5d','fb5d_log_r1'), ('13f5','13f5_log_r1'), ('6d18','6d18_log_r1'), ('7353','7353_log_r1')]:
    fed = set(int(l.split()[1]) for l in open(wob.W + '/runs/%s.map' % tag))
    ark = wob.load_arkit(sc)
    tr = {n: load_tum(wob.W + '/stats/tum_%s_%s.tum' % (tag, n), fed) for n in ('api', 'latest', 'kf')}
    common = set.intersection(*[set(v['tns'].tolist()) for v in tr.values()])
    for n, v in tr.items():
        sel = np.isin(v['tns'], list(common))
        v = {k: x[sel] for k, x in v.items()}
        J = wob.join(v, ark); kg = wob.k_sim3(J['X'], J['Y']); ate = 100 * wob.ate_sim3(J['X'], J['Y'])
        s5 = seg_stats(J, kg, 5.0, 5.0); sl = seg_stats(J, kg, 5.0, 1.0); s2 = seg_stats(J, kg, 2.0, 2.0)
        e5 = np.array([e for _, e in s5]); el = np.array([e for _, e in sl]); e2 = np.array([e for _, e in s2])
        res[f'{sc}:{n}'] = dict(k_vs_arkit=kg, ate_cm=ate, seg5=[(round(a,1), e) for a, e in s5], slide5=[(round(a,1), e) for a, e in sl])
        print('%-5s %-6s n %3d  k/ARKit %.4f  ATE %.2f cm | 5s 不重叠 %s | 5s 滑窗 min %+.1f%% max %+.1f%% sd %.1f%% | 2s sd %.1f%%' % (
            sc, n, len(J['t']), kg, ate, ' '.join('%+.1f' % (100 * e) for e in e5), 100 * el.min(), 100 * el.max(), 100 * el.std(), 100 * e2.std()))
json.dump(res, open(wob.W + '/stats/seg5_vs_arkit.json', 'w'), indent=1, default=float)
