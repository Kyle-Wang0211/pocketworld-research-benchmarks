#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 加计前移轮] 扫参评分(只读):每个回放(场 × 加计前移 × td)的
  后端定稿(kind 2,收尾窗口帧取 kind 3;10 Hz)与前端(keyed.csv,全速率):
    对陀螺 g / 抖动(wobble/tools/gyrofit.py 原样调用);对 ARKit 的尺度 k 与 ATE(scale_eval.estimators,与 eval3 同估计器);
    链到 LiDAR = k × 米尺报告里 ARKit 的 k。
选 td 的判据 = 积分 agent 选 Δ=−5 时用的同一判据:后端定稿旋转抖动的三场均值,取最小的共同 Δ(另列 ATE 三场和作参考)。
基线行:上一轮 newrun/<scene>_new_r1(前移 0、td −5)。
用法:sweep_as_eval.py"""
import csv, glob, json, os, re, sys
import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
O = SP + '/offline_sfm'
sys.path.insert(0, SP + '/wobble/tools')
import gyrofit as GF  # noqa: E402
import wob  # noqa: E402
sys.path.insert(0, O + '/tools')
import analyze_run as AR  # noqa: E402
import make_feeds as MF  # noqa: E402
GRID = np.arange(-0.03, 0.0301, 0.0005)


def load_run(path):
    fin, win = {}, {}
    for r in csv.DictReader(open(path + '.backend.csv')):
        if r['t_ns'] == '-1':
            continue
        v = (int(r['t_ns']), MF.q2R(float(r['qw']), float(r['qx']), float(r['qy']), float(r['qz'])),
             np.array([float(r[k]) for k in ('tx', 'ty', 'tz')]))
        if r['kind'] == '2':
            fin[v[0]] = v
        elif r['kind'] == '3':
            win[v[0]] = v
    d = dict(win); d.update(fin)
    fr = []
    for r in csv.DictReader(open(path + '.keyed.csv')):
        fr.append((int(r['t_ns']), MF.q2R(float(r['qw']), float(r['qx']), float(r['qy']), float(r['qz'])),
                   np.array([float(r[k]) for k in ('tx', 'ty', 'tz')])))
    return sorted(d.values(), key=lambda x: x[0]), fr


def metrics(scene, traj, G, arkC, kA, gap):
    t = np.array([x[0] for x in traj], dtype=np.int64); R = np.array([x[1] for x in traj])
    f = GF.fit(G, *GF.increments(t, R, gap), GRID)
    keep = [x for x in traj if x[0] in arkC]
    X = np.array([x[2] for x in keep]).T; Y = np.array([arkC[x[0]] for x in keep]).T
    e = AR.SE['estimators'](X, Y)
    return {'g': f['g'], 'jitter': f['jitter_deg'], 's_ms': f['s_ms'], 'k_pct': 100 * (e['k_sim3_fwd'] - 1),
            'kL_pct': 100 * (e['k_sim3_fwd'] * kA - 1), 'ate_cm': e['ate_sim3_cm']}


def main():
    runs = {}
    for p in sorted(glob.glob(f'{O}/asrun/*_as*_td*.backend.csv')):
        m = re.match(r'(\w{4})_as(\d+)_td(-?\d+)$', os.path.basename(p)[:-len('.backend.csv')])
        if m:
            runs[(m.group(1), int(m.group(2)), int(m.group(3)))] = p[:-len('.backend.csv')]
    for s in ('13f5', '6d18', '7353'):
        runs[(s, 0, -5)] = f'{O}/newrun/{s}_new_r1'
    res = {}
    cache = {}
    for (s, a, td), path in sorted(runs.items()):
        if s not in cache:
            ark = wob.load_arkit(s)
            cache[s] = (GF.GyroInt(s), dict(zip(ark['tns'].tolist(), ark['P'])), AR.k_arkit_lidar(s))
        G, arkC, kA = cache[s]
        bk, fr = load_run(path)
        res[f'{s}|{a}|{td}'] = {'backend_final': metrics(s, bk, G, arkC, kA, 0.4), 'front': metrics(s, fr, G, arkC, kA, 0.2)}
    json.dump(res, open(f'{O}/sweep_as.json', 'w'), indent=1, ensure_ascii=False)
    print('场 | 加计前移 ms | td Δ ms | 后端定稿:抖动° g k对ARKit k对LiDAR ATE cm | 前端:抖动° g k对LiDAR ATE cm')
    for k in sorted(res, key=lambda x: (x.split('|')[0], int(x.split('|')[1]), -int(x.split('|')[2]))):
        s, a, td = k.split('|'); b = res[k]['backend_final']; f = res[k]['front']
        print(f"{s} | {a:>2} | {int(td):+d} | {b['jitter']:.4f} {b['g']:.4f} {b['k_pct']:+.2f}% {b['kL_pct']:+.2f}% {b['ate_cm']:.2f} | "
              f"{f['jitter']:.4f} {f['g']:.4f} {f['kL_pct']:+.2f}% {f['ate_cm']:.2f}")
    print()
    for a in sorted({int(k.split('|')[1]) for k in res}):
        tds = sorted({int(k.split('|')[2]) for k in res if int(k.split('|')[1]) == a})
        rows = []
        for td in tds:
            ks = [f'{s}|{a}|{td}' for s in ('13f5', '6d18', '7353')]
            if not all(k in res for k in ks):
                continue
            jm = np.mean([res[k]['backend_final']['jitter'] for k in ks])
            ate = sum(res[k]['backend_final']['ate_cm'] for k in ks)
            kl = np.sqrt(np.mean([res[k]['backend_final']['kL_pct'] ** 2 for k in ks]))
            fj = np.mean([res[k]['front']['jitter'] for k in ks])
            fate = sum(res[k]['front']['ate_cm'] for k in ks)
            rows.append((td, jm, ate, kl, fj, fate))
        if not rows:
            continue
        best = min(rows, key=lambda r: r[1])
        print(f'加计前移 {a} ms:' + ';'.join(f'Δ{r[0]:+d}: 后端抖动均值 {r[1]:.4f}° ATE和 {r[2]:.2f} cm 对LiDAR RMS {r[3]:.2f}% | 前端抖动 {r[4]:.4f}° 前端ATE和 {r[5]:.2f}' for r in rows))
        print(f'  ⇒ 判据(后端定稿抖动三场均值最小)选 Δ = {best[0]:+d} ms;ATE 三场和最小的是 Δ = {min(rows, key=lambda r: r[2])[0]:+d} ms')


if __name__ == '__main__':
    main()
