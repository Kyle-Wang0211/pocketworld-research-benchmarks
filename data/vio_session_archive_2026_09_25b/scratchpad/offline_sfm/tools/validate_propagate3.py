#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 新引擎轮] xr_propagate2 的可失败验证(与 validate_propagate2.py 同一方法,状态改取新引擎后端 CSV)。
后端第 b 帧定稿状态(backend.csv kind 2:body 位姿 + v bg ba)外推到下一个后端帧 b+1 的时刻,与 b+1 的定稿 body 位姿比。
负对照:v 置零;四元数按 (w,x,y,z) 误读;ba 取反。另附:同一方法用旧工具 xr_propagate(旧离散)跑同一组新状态,
看新旧离散在同一输入上差多少(不是对照组,只是量级参考)。
用法:validate_propagate3.py <scene> <run tag>"""
import csv, os, subprocess, sys
import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
O = SP + '/offline_sfm'
RECS = {'13f5': 'run-13f53d2f-5935-4b1a-a499-4dc8367ea935', '6d18': 'run-6d187dff-403a-4882-b692-7bdc6c3cfa2a',
        '7353': 'run-73538ad6-8418-4eaf-8b75-a63c9d32af46'}


def q2R(x, y, z, w):
    n = np.sqrt(w*w + x*x + y*y + z*z); w, x, y, z = w/n, x/n, y/n, z/n
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def ang(Ra, Rb):
    return np.degrees(np.arccos(np.clip((np.trace(Ra.T @ Rb) - 1) / 2, -1, 1)))


def load_final(path):
    fin = {}
    for r in csv.DictReader(open(path)):
        if r['kind'] == '2' and r['t_ns'] != '-1':
            fin[float(r['engine_t'])] = {
                'p': [float(r[k]) for k in ('body_tx', 'body_ty', 'body_tz')],
                'q': [float(r[k]) for k in ('body_qx', 'body_qy', 'body_qz', 'body_qw')],
                'v': [float(r[k]) for k in ('vx', 'vy', 'vz')],
                'bg': [float(r[k]) for k in ('bgx', 'bgy', 'bgz')],
                'ba': [float(r[k]) for k in ('bax', 'bay', 'baz')]}
    return fin


def main():
    scene, tag = sys.argv[1], sys.argv[2]
    rec = os.path.expanduser('~/Developer/viobench-recordings/' + RECS[scene])
    kf = load_final(f'{O}/newrun/{tag}.backend.csv')
    ts = sorted(kf)
    variants = {'正确': lambda d: (d['q'], d['v'], d['ba']),
                '负对照_v置零': lambda d: (d['q'], [0, 0, 0], d['ba']),
                '负对照_四元数按wxyz误读': lambda d: ([d['q'][1], d['q'][2], d['q'][3], d['q'][0]], d['v'], d['ba']),
                '负对照_ba取反': lambda d: (d['q'], d['v'], [-x for x in d['ba']])}
    for tool in ('xr_propagate2', 'xr_propagate'):
        for name, fn in variants.items():
            if tool == 'xr_propagate' and name != '正确':
                continue
            jobs = []
            for a, b in zip(ts[:-1], ts[1:]):
                if b - a > 0.2:
                    continue
                q, v, ba = fn(kf[a])
                x = [a] + kf[a]['p'] + q + v + kf[a]['bg'] + ba + [b]
                jobs.append(f'{a:.9f} ' + ' '.join('%.17g' % y for y in x))
            jp, op = f'{O}/tmp_v3_{scene}.jobs', f'{O}/tmp_v3_{scene}.out'
            open(jp, 'w').write('\n'.join(jobs) + '\n')
            subprocess.run([f'{O}/build/{tool}', f'{SP}/preint/cfg/slam_config.yaml', f'{SP}/preint/cfg/dev_{scene}.yaml',
                            rec + '/imu.csv', jp, op], check=True, stderr=subprocess.DEVNULL)
            ep, er, lag = [], [], []
            for l in open(op):
                f = l.split()
                tt = float(f[2]); t_last = float(f[3])
                b = min(kf, key=lambda k: abs(k - tt))
                bp = np.array([float(x) for x in f[5:8]]); bq = [float(x) for x in f[8:12]]
                ep.append(np.linalg.norm(bp - np.array(kf[b]['p'])))
                er.append(ang(q2R(*bq), q2R(*kf[b]['q'])))
                lag.append(1e3 * (tt - t_last))
            ep = 1e3 * np.array(ep); er = np.array(er)
            lab = name if tool == 'xr_propagate2' else '参考:旧离散工具(同一组新状态)'
            print(f'{scene} {lab}: {len(ep)} 对;位置差 中位 {np.median(ep):.2f} mm p95 {np.percentile(ep, 95):.2f} 最大 {ep.max():.2f};'
                  f'旋转差 中位 {np.median(er):.3f}° p95 {np.percentile(er, 95):.3f}° 最大 {er.max():.3f}°;'
                  f'外推终点距目标 中位 {np.median(lag):.2f} ms')
            os.remove(jp); os.remove(op)


if __name__ == '__main__':
    main()
