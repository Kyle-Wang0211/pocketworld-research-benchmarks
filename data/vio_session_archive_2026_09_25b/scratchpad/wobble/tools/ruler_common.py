import json, numpy as np
W='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble'
NAMES = ['arkit','api','latest','kf']
res = {}
for sc in ['fb5d','13f5','6d18','7353']:
    J = json.load(open(f'{W}/stats/ruler_{sc}/lidar_ruler_report.json')); T = J['trajectories']
    P = {n: T[n]['pairs'] for n in NAMES}
    npair = len(P['arkit'])
    ok = [i for i in range(npair) if all('scale_to_metric' in P[n][i] for n in NAMES)]
    t0 = P['arkit'][0]['t_a']
    ta = np.array([P['arkit'][i]['t_a'] - t0 for i in ok])
    K = {n: np.array([1/P[n][i]['scale_to_metric'] for i in ok]) for n in NAMES}
    tall = np.array([p['t_a'] - t0 for p in P['arkit']])
    print('== %s 帧对 %d(时间 %.1f–%.1f s),四条共同有效 %d(时间 %.1f–%.1f s)' % (sc, npair, tall.min(), tall.max(), len(ok), ta.min(), ta.max()))
    parts = np.array_split(np.arange(len(ok)), 4)
    for n in NAMES:
        kf = np.median(K[n]); q = [np.median(K[n][p]) for p in parts]
        rel = np.array(q) / kf
        r_ark = K[n] / K['arkit']
        qa = [np.median(r_ark[p]) for p in parts]
        print('  %-6s 全场 k %.4f | 四分段(对LiDAR) %s | 段/全场 %s 极差 %.1f%% | 逐对 k/k_ARKit 四分段 %s 极差 %.1f%% | 逐对比稳健sd %.1f%%' % (
            n, kf, ' '.join('%.3f' % x for x in q), ' '.join('%+.1f' % (100*(x-1)) for x in rel), 100*(rel.max()-rel.min()),
            ' '.join('%.3f' % x for x in qa), 100*(max(qa)-min(qa)) if n != 'arkit' else 0, 100*1.4826*np.median(np.abs(r_ark-np.median(r_ark))) if n!='arkit' else 0))
    print('  四分段时间范围(s):', ' '.join('[%.1f,%.1f]' % (ta[p].min(), ta[p].max()) for p in parts))
