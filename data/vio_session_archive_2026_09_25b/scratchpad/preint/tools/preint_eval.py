#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 积分方式改前改后评分(只读)。每个回放 tag × {前端, 后端首次, 后端定稿} 给:
  · 对陀螺:时间偏移 s(相对引擎时间戳 = PTS + exposure/2 + c,每帧用自己的 engine_t)、幅度比 g、
    每增量旋转抖动(最优 s 下残差 RMS,°/增量)—— 方法照抄 wobble/tools/gyrofit.py(fit/GyroInt 直接 import);
  · 对 ARKit:k(scale_eval 前向 Sim3,k = XR 尺度 / ARKit 尺度)、ATE、5 s 分段、2 s 窗尺度抖动
    —— k/ATE/5 s 分段照抄 bkpose/tools/eval3.py(直接 import),2 s 窗同一写法换窗长;
  · 链式到 LiDAR:k_LiDAR = k_ARKit × (1 + ARKit 对 LiDAR 偏差),偏差取任务给定值。
ARKit 两行:全帧(33 ms 增量)与只取后端帧(同一批帧、同口径)。
用法:preint_eval.py <scene> <tag> [--json out]
"""
import csv
import json
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/wobble/tools')
sys.path.insert(0, SP + '/preint/tools')
import eval3  # noqa: E402  (W = preint/runs)
import gyrofit  # noqa: E402
import wob  # noqa: E402
from rotcal import logm  # noqa: E402

W = SP + '/preint/runs/'
ARK_VS_LIDAR = {'13f5': -0.0222, '6d18': -0.0394, '7353': -0.0062}
REC = {k: wob.R + '/' + v for k, v in wob.REC.items()}
D = np.diag([1.0, -1.0, -1.0])


def load_keyed_full(p):
    out = {}
    for r in csv.DictReader(open(p)):
        out[int(r['t_ns'])] = (eval3._R(r), np.array([float(r['tx']), float(r['ty']), float(r['tz'])]),
                               float(r['engine_t']))
    return out


def load_backend_full(p):
    first, final, window = {}, {}, {}
    for r in csv.DictReader(open(p)):
        t = int(r['t_ns'])
        if t < 0:
            continue
        c = (eval3._R(r), np.array([float(r['tx']), float(r['ty']), float(r['tz'])]), float(r['engine_t']))
        if r['kind'] == '1':
            first.setdefault(t, c)
        elif r['kind'] == '2':
            final[t] = c
        elif r['kind'] == '3':
            window[t] = c
    fin = dict(window)
    fin.update(final)
    return first, fin


def gyro(G, est, key, max_gap, grid):
    """est: {t_ns: (R, p, engine_t)};key='engine' ⇒ 时间用 engine_t,'pts' ⇒ 用 t_ns。"""
    ts = sorted(est)
    t = np.array([est[k][2] if key == 'engine' else k * 1e-9 for k in ts])
    R = np.array([est[k][0] for k in ts])
    keep = np.nonzero(np.diff(t) < max_gap)[0]
    th = np.array([logm(R[i].T @ R[i + 1]) for i in keep])
    return gyrofit.fit(G, t[keep], t[keep + 1], th, grid)


def as_pose_dict(est):
    return {k: (v[0], v[1]) for k, v in est.items()}


def win_k(est, ark, win):
    ts = sorted(set(est) & set(ark))
    X = np.array([est[t][1] for t in ts]).T
    Y = np.array([ark[t][1] for t in ts]).T
    t = np.array(ts) * 1e-9
    r = eval3.SE['estimators'](X, Y)
    wk = eval3.windows_k(t, X, Y, r['k_sim3_fwd'], win, 5 if win <= 2.0 else 10)
    e = np.array([w[2] for w in wk])
    return e


def run(sc, tag, grid=np.arange(-0.03, 0.0301, 0.0005)):
    rec = REC[sc]
    frame_ts = [int(l.split(',')[0]) for l in open(rec + '/camera_index.csv').read().split('\n')[1:] if l]
    ark, _ = eval3.LR.arkit_poses(rec, rec + '/arkit_poses.tum', frame_ts)
    front = load_keyed_full(W + tag + '.keyed.csv')
    first, final = load_backend_full(W + tag + '.backend.csv')
    bset = set(first)
    G = gyrofit.GyroInt(sc)
    # ARKit 旋转(相机,转成与 gyrofit 相同的约定;Kabsch 会吸收常量旋转,D 不影响抖动)
    A = wob.load_arkit(sc)
    RA = wob.qmat(A['Q']) @ D
    ark_rot = {int(t): (RA[i], A['P'][i], int(t) * 1e-9) for i, t in enumerate(A['tns'])}
    ark_rot_b = {k: v for k, v in ark_rot.items() if k in bset}
    res = {'scene': sc, 'tag': tag, 'n_front': len(front), 'n_first': len(first), 'n_final': len(final)}
    rows = {}
    for name, est, gap in (('front', front, 0.2), ('backend_first', first, 0.4), ('backend_final', final, 0.4)):
        m = eval3.metrics(as_pose_dict(est), ark, 30 if name == 'front' else 10)
        gy = gyro(G, est, 'engine', gap, grid)
        gp = gyro(G, est, 'pts', gap, grid)
        e2 = win_k(as_pose_dict(est), ark, 2.0)
        k = m['k']
        rows[name] = dict(s_engine_ms=gy['s_ms'], s_pts_ms=gp['s_ms'], g=gy['g'], jitter_deg=gy['jitter_deg'],
                          n_inc=gy['n'], k_ark=k, k_lidar=k * (1 + ARK_VS_LIDAR[sc]), ate_cm=m['ate_cm'],
                          seg5_min=m['seg5_min_pct'], seg5_max=m['seg5_max_pct'], seg5_sd=m['seg5_sd_pct'],
                          win2_sd=float(100 * e2.std()), win2_absmax=float(100 * np.abs(e2).max()),
                          relrot_med=m['rel_rot_err_deg_med'], n=m['n'])
    ga = gyrofit.fit(G, *gyrofit.increments(A['tns'], RA, 0.2), grid)
    tb = np.array(sorted(ark_rot_b))
    gb = gyrofit.fit(G, *gyrofit.increments(tb, np.array([ark_rot_b[k][0] for k in tb]), 0.4), grid)
    rows['arkit_all'] = dict(s_pts_ms=ga['s_ms'], g=ga['g'], jitter_deg=ga['jitter_deg'], n_inc=ga['n'])
    rows['arkit@backend'] = dict(s_pts_ms=gb['s_ms'], g=gb['g'], jitter_deg=gb['jitter_deg'], n_inc=gb['n'])
    res['rows'] = rows
    return res


def fmt(res):
    out = []
    for name, r in res['rows'].items():
        if name.startswith('arkit'):
            out.append('%-5s %-18s %-14s s(PTS) %+6.2f ms  g %.4f  抖动 %.4f°  n %d' % (
                res['scene'], res['tag'], name, r['s_pts_ms'], r['g'], r['jitter_deg'], r['n_inc']))
        else:
            out.append('%-5s %-18s %-14s s(引擎) %+6.2f ms s(PTS) %+6.2f  g %.4f  抖动 %.4f°  k_ARKit %+.2f%%  k_LiDAR %+.2f%%  '
                       'ATE %.2f cm  5s %+.1f…%+.1f sd %.1f%%  2s sd %.1f%% max %.1f%%  n %d' % (
                           res['scene'], res['tag'], name, r['s_engine_ms'], r['s_pts_ms'], r['g'], r['jitter_deg'],
                           100 * (r['k_ark'] - 1), 100 * (r['k_lidar'] - 1), r['ate_cm'], r['seg5_min'], r['seg5_max'],
                           r['seg5_sd'], r['win2_sd'], r['win2_absmax'], r['n']))
    return '\n'.join(out)


if __name__ == '__main__':
    sc, tag = sys.argv[1], sys.argv[2]
    res = run(sc, tag)
    print(fmt(res))
    if len(sys.argv) > 4 and sys.argv[3] == '--json':
        json.dump(res, open(sys.argv[4], 'w'), indent=1, ensure_ascii=False)
