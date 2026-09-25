#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 LiDAR 尺子(--camera 入口)写三种 XR 相机位姿 TUM,时间 = 录制帧 t_ns(整数纳秒精确写出):
  api      对外输出(XRSLAM_RESULT_CAMERA_POSE);该帧被 XR 收下且有位姿 ⇒ 原样,否则按引擎时间在相邻输出间插值
  latest   后端每次求解后窗内最新帧状态(插桩 ev=latest),陀螺 + Hermite 插值到目标帧
  kf       关键帧边缘化前的终值(插桩 ev=kf_final),同上
目标帧:录制 ruler_subset 的全部帧 + 全部被 XR 收下的帧(后者给 ATE/分窗)。
引擎时间 = t_ns + exposure/2 + c(c = yaml cam0.time_offset + td_extra),与 pwvi_runner 同式。
"""
import json
import re
import sys

import numpy as np

sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob  # noqa: E402
from rotcal import logm, expm  # noqa: E402
from gyrofit import GyroInt  # noqa: E402
from backend_eval import yaml_ext  # noqa: E402
from calib_joint_q import r2q  # noqa: E402


def engine_time_fn(sc, tag):
    cmd = open(wob.W + '/runs/%s.cmd' % tag).read()
    dev = re.search(r'dev=(\S+)', cmd).group(1)
    c = float(re.search(r'time_offset:\s*([-0-9.eE]+)', open(wob.W + '/cfg/' + dev).read()).group(1))
    m = re.search(r'--td-extra-ms\s+([-0-9.]+)', cmd)
    c += float(m.group(1)) * 1e-3 if m else 0.0
    I = wob.load_intr(sc)
    ex = dict(zip(I['tns'].tolist(), I['exp'].tolist()))

    def f(tn):
        t_out = tn + int(np.rint(0.5 * ex[tn] * 1e9))
        return float(repr(t_out * 1e-9)) + c if False else t_out * 1e-9 + c
    return f


def states(tag, ev):
    S = {}
    for ln in open(wob.W + '/runs/%s.jsonl' % tag):
        try:
            d = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if d['ev'] != ev:
            continue
        S.setdefault(d['t'], (d['t'], wob.qmat(np.array([d['q']]))[0], np.array(d['p']), np.array(d['v']),
                              np.array(d.get('bg', [0, 0, 0]))))
    return sorted(S.values(), key=lambda x: x[0])


def interp_backend(G, st, t, Rbc, pbc, max_gap=0.25):
    te = np.array([s[0] for s in st])
    i = np.searchsorted(te, t) - 1
    if i < 0 or i + 1 >= len(te) or te[i + 1] - te[i] > max_gap:
        return None
    t0, R0, p0, v0, bg0 = st[i]; t1, R1, p1, v1, _ = st[i + 1]
    h = t1 - t0; a = (t - t0) / h
    F = lambda x: G.F(np.array([x]))[0]  # noqa: E731
    dR01 = expm(F(t1) - F(t0) - bg0 * h)
    res = logm(dR01.T @ (R0.T @ R1))
    R = R0 @ expm(F(t) - F(t0) - bg0 * (t - t0)) @ expm(a * res)
    h00 = 2 * a ** 3 - 3 * a ** 2 + 1; h10 = a ** 3 - 2 * a ** 2 + a; h01 = -2 * a ** 3 + 3 * a ** 2; h11 = a ** 3 - a ** 2
    p = h00 * p0 + h10 * h * v0 + h01 * p1 + h11 * h * v1
    return R @ Rbc, p + R @ pbc


def interp_api(te, Rs, Ps, t, max_gap=0.1):
    i = np.searchsorted(te, t) - 1
    if i < 0 or i + 1 >= len(te):
        return None
    if abs(te[i] - t) < 1e-7:
        return Rs[i], Ps[i]
    if abs(te[i + 1] - t) < 1e-7:
        return Rs[i + 1], Ps[i + 1]
    if te[i + 1] - te[i] > max_gap:
        return None
    a = (t - te[i]) / (te[i + 1] - te[i])
    R = Rs[i] @ expm(a * logm(Rs[i].T @ Rs[i + 1]))
    return R, (1 - a) * Ps[i] + a * Ps[i + 1]


def fmt_t(tn):
    return '%d.%09d' % (tn // 1_000_000_000, tn % 1_000_000_000)


def write(sc, tag, out_prefix):
    Rbc, pbc = yaml_ext(tag)
    eng = engine_time_fn(sc, tag)
    G = GyroInt(sc)
    sub = np.loadtxt(wob.rdir(sc) + '/ruler_subset/camera_index.csv', delimiter=',', skiprows=1, dtype=np.int64)[:, 0]
    fed = [int(l.split()[1]) for l in open(wob.W + '/runs/%s.map' % tag)]
    targets = sorted(set(sub.tolist()) | set(fed))
    C = np.loadtxt(wob.W + '/runs/%s.cam.tum' % tag)
    C = C[np.linalg.norm(C[:, 4:8], axis=1) > 0.5]
    te = C[:, 0]; Rs = wob.qmat(C[:, 4:8]); Ps = C[:, 1:4]
    sts = {'latest': states(tag, 'latest'), 'kf': states(tag, 'kf_final')}
    files = {}
    for name in ('api', 'latest', 'kf'):
        rows = []
        for tn in targets:
            t = eng(tn)
            r = interp_api(te, Rs, Ps, t) if name == 'api' else interp_backend(G, sts[name], t, Rbc, pbc)
            if r is None:
                continue
            R, p = r
            q = r2q(R)
            rows.append('%s %.7f %.7f %.7f %.7f %.7f %.7f %.7f' % (fmt_t(tn), *p, *q))
        fn = '%s_%s.tum' % (out_prefix, name)
        open(fn, 'w').write('\n'.join(rows) + '\n')
        files[name] = (fn, len(rows))
    return files, len(sub)


if __name__ == '__main__':
    for a in sys.argv[1:]:
        sc, tag = a.split(':')
        files, nsub = write(sc, tag, wob.W + '/stats/tum_%s' % tag)
        print(sc, tag, '子集帧', nsub, {k: v[1] for k, v in files.items()})
