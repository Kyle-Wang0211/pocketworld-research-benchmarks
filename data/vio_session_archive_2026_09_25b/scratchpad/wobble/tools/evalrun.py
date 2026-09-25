#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次回放一行:全局 k(对 ARKit)、ATE、四段、2 s 不重叠窗 |误差| 中位/最大、4 s 滑窗 sd、位移比 sd、XR/陀螺旋转幅度。
用法:evalrun.py sc:tag [sc:tag ...]   (tag=phone 取手机回放)
"""
import json
import sys

import numpy as np

sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob  # noqa: E402
import rotcal  # noqa: E402


def metrics(sc, xr):
    ark = wob.load_arkit(sc)
    J = wob.join(xr, ark)
    kg = wob.k_sim3(J['X'], J['Y'])
    ate = 100 * wob.ate_sim3(J['X'], J['Y'])
    q = wob.quarters(J)
    w2 = wob.windows(J, 2.0, 2.0)
    e2 = np.array([w['k_sim3'] / kg - 1 for w in w2])
    kdg, _ = wob.disp_ratio(J['t'], J['X'], J['Y'], 0.5)
    d2 = np.array([w['k_disp'] / kdg - 1 for w in w2])
    w4 = wob.windows(J, 4.0, 0.5)
    e4 = np.array([w['k_sim3'] / kg - 1 for w in w4])
    # XR/陀螺 旋转幅度(0.5 s 区间,M 对角均值)
    A = rotcal.run(sc, xr)
    M, b, rms = rotcal.fit(A[:, 8:11], A[:, 5:8], A[:, 1])
    return dict(n=len(J['t']), k=kg, ate_cm=ate, q=q, e2_med=np.median(np.abs(e2)), e2_max=np.max(np.abs(e2)),
                e2_sd=np.std(e2), d2_sd=np.std(d2), e4_sd=np.std(e4), e4_min=e4.min(), e4_max=e4.max(),
                rot_scale=float(np.mean(np.diag(M))), e2=e2.tolist(), d2=d2.tolist())


def fmt(sc, tag, m):
    return ('%-5s %-24s n %4d k %.4f ATE %5.2f | Q %s | 2s|e| med %4.1f%% max %4.1f%% sd %4.1f%% disp-sd %4.1f%% | 4s sd %4.1f%% [%+.1f,%+.1f] | rot×%.4f' % (
        sc, tag, m['n'], m['k'], m['ate_cm'], ' '.join('%.3f' % x for x in m['q']), 100 * m['e2_med'], 100 * m['e2_max'],
        100 * m['e2_sd'], 100 * m['d2_sd'], 100 * m['e4_sd'], 100 * m['e4_min'], 100 * m['e4_max'], m['rot_scale']))


if __name__ == '__main__':
    out = {}
    for a in sys.argv[1:]:
        sc, tag = a.split(':')
        try:
            xr = wob.load_xr_phone(sc) if tag == 'phone' else wob.load_xr_mac(tag)
            m = metrics(sc, xr)
        except Exception as ex:  # noqa: BLE001
            print('%-5s %-24s 失败 %s' % (sc, tag, ex))
            continue
        print(fmt(sc, tag, m), flush=True)
        out[a] = m
    if out:
        p = wob.W + '/stats/evalrun_%s.json' % abs(hash(tuple(sys.argv[1:])))
        json.dump(out, open(p, 'w'), default=float)
