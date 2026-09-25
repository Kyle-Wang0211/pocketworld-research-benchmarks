import json, sys, numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob
W = wob.W
def load_tum(fn, keep):
    tns, P, Q = [], [], []
    for l in open(fn):
        f = l.split()
        if not f: continue
        s, fr = f[0].split('.'); t = int(s) * 10**9 + int(fr)
        if t not in keep: continue
        tns.append(t); P.append([float(x) for x in f[1:4]]); Q.append([float(x) for x in f[4:8]])
    return dict(tns=np.array(tns, dtype=np.int64), P=np.array(P), Q=np.array(Q))
out = {}
print('场景 位姿   尺子全场k(判定)   桥接全场k   ATE对ARKit | 5 s 分段对 LiDAR(桥接,段/全场 %)            min    max    sd')
for sc, tag in [('fb5d','fb5d_log_r1'), ('13f5','13f5_log_r1'), ('6d18','6d18_log_r1'), ('7353','7353_log_r1')]:
    R = json.load(open(f'{W}/stats/ruler_{sc}/lidar_ruler_report.json'))['trajectories']
    ap = [p for p in R['arkit']['pairs'] if 'scale_to_metric' in p]
    at = np.array([p['t_a'] for p in ap]); ak = 1 / np.array([p['scale_to_metric'] for p in ap])
    k_ark = R['arkit']['estimate']['k']
    fed = set(int(l.split()[1]) for l in open(f'{W}/runs/{tag}.map'))
    ark = wob.load_arkit(sc)
    T = {n: load_tum(f'{W}/stats/tum_{tag}_{n}.tum', fed) for n in ('api', 'latest', 'kf')}
    common = set.intersection(*[set(v['tns'].tolist()) for v in T.values()])
    for n, v in T.items():
        sel = np.isin(v['tns'], list(common)); v = {k: x[sel] for k, x in v.items()}
        J = wob.join(v, ark); kg = wob.k_sim3(J['X'], J['Y']); ate = 100 * wob.ate_sim3(J['X'], J['Y'])
        t = J['t']; segs = []
        a = t[0]
        while a + 5.0 <= t[-1] + 1e-6:
            m = (t >= a) & (t < a + 5.0)
            ma = (at >= a) & (at < a + 5.0)
            k_xa = wob.k_sim3(J['X'][:, m], J['Y'][:, m])
            k_al = np.median(ak[ma]) if ma.sum() >= 3 else k_ark
            segs.append((a - t[0], k_xa * k_al, int(ma.sum())))
            a += 5.0
        kb = kg * k_ark
        rel = np.array([s[1] for s in segs]) / kb - 1
        e = R[n]['estimate']
        print('%-5s %-6s %.4f(%s)  %.4f    %.2f cm | %s | %+5.1f  %+5.1f  %4.1f' % (
            sc, n, e['k'], '有效' if R[n]['verdict'] == 'valid' else '未过闸', kb, ate,
            ' '.join('%+.1f' % (100 * r) for r in rel), 100 * rel.min(), 100 * rel.max(), 100 * rel.std()))
        out[f'{sc}:{n}'] = dict(k_ruler=e['k'], verdict=R[n]['verdict'], k_bridge=kb, ate_cm=ate,
                                seg5_rel=rel.tolist(), seg5_abs=[s[1] for s in segs], seg5_ark_pairs=[s[2] for s in segs])
    print('%-5s arkit  %.4f(%s)   ARKit 5 s 段对 LiDAR:%s' % (sc, k_ark, '有效' if R['arkit']['verdict']=='valid' else '未过闸',
          ' '.join('%.3f(%d)' % (np.median(ak[(at >= a) & (at < a + 5)]) if ((at >= a) & (at < a + 5)).sum() else np.nan, ((at >= a) & (at < a + 5)).sum()) for a in np.arange(at.min(), at.max(), 5.0))))
json.dump(out, open(f'{W}/stats/bridge5.json', 'w'), indent=1, default=float)
