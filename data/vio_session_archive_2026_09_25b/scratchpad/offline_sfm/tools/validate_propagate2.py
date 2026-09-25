#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 外推轮] 外推工具的可失败验证(第二版)。
第一版假设「前端输出 = latest 后端状态 + propagate_state」,不成立:XRSLAM_LOWLATENCY_POSE 下前端先用
Preintegrator::predict 逐帧推到最新跟踪帧(feature_tracker.cpp:64-78, 106-116),再 propagate_state。
这里改为:后端第 b 帧定稿状态(kf_final:p q v bg ba)用 xr_propagate 推到下一个后端帧 b+1 的时刻,
和 b+1 自己的定稿位姿比。后端优化里 IMU 因子把相邻帧拉在一起 ⇒ 正确实现应在毫米 / 零点几度量级。
负对照(必须明显变差):v 置零;四元数按 (w,x,y,z) 误读;加速度计零偏符号取反(小,看灵敏度)。
负对照只改喂给工具的输入,工具本身不动。
用法:validate_propagate2.py <scene>"""
import json, os, subprocess, sys
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


def main():
    scene = sys.argv[1]
    rec = os.path.expanduser('~/Developer/viobench-recordings/' + RECS[scene])
    kf = {}
    for l in open(f'{SP}/wobble/runs/{scene}_log_r1.jsonl'):
        if '"kf_final"' in l:
            d = json.loads(l); kf[d['t']] = d
    ts = sorted(kf)
    variants = {'正确': lambda d: (d['q'], d['v'], d['ba']),
                '负对照_v置零': lambda d: (d['q'], [0, 0, 0], d['ba']),
                '负对照_四元数按wxyz误读': lambda d: ([d['q'][1], d['q'][2], d['q'][3], d['q'][0]], d['v'], d['ba']),
                '负对照_ba取反': lambda d: (d['q'], d['v'], [-x for x in d['ba']])}
    for name, fn in variants.items():
        jobs = []
        for a, b in zip(ts[:-1], ts[1:]):
            if b - a > 0.2:
                continue
            q, v, ba = fn(kf[a])
            x = [a] + kf[a]['p'] + q + v + kf[a]['bg'] + ba + [b]
            jobs.append(f'{a:.9f} ' + ' '.join('%.17g' % y for y in x))
        jp, op = f'{O}/tmp_v2_{scene}.jobs', f'{O}/tmp_v2_{scene}.out'
        open(jp, 'w').write('\n'.join(jobs) + '\n')
        subprocess.run([f'{O}/build/xr_propagate', f'{SP}/bkpose/cfg/slam_config.yaml', f'{SP}/bkpose/cfg/dev_{scene}.yaml',
                        rec + '/imu.csv', jp, op], check=True, stderr=subprocess.DEVNULL)
        ep, er, dts, nimu = [], [], [], []
        for l in open(op):
            f = l.split()
            a = float(f[0]); tt = float(f[2]); t_last = float(f[3]); nimu.append(int(f[4]))
            b = min(kf, key=lambda k: abs(k - tt))
            bp = np.array([float(x) for x in f[5:8]]); bq = [float(x) for x in f[8:12]]
            ep.append(np.linalg.norm(bp - np.array(kf[b]['p'])))
            er.append(ang(q2R(*bq), q2R(*kf[b]['q'])))
            dts.append(1e3 * (tt - t_last))
        ep = 1e3 * np.array(ep); er = np.array(er)
        print(f'{scene} {name}: 相邻后端帧 {len(ep)} 对,外推 {np.median(nimu):.0f} 个 IMU 样本(中位);'
              f'位置差 中位 {np.median(ep):.2f} mm p95 {np.percentile(ep, 95):.2f} 最大 {ep.max():.2f};'
              f'旋转差 中位 {np.median(er):.3f}° p95 {np.percentile(er, 95):.3f}° 最大 {er.max():.3f}°;'
              f'末样本距目标时刻 中位 {np.median(dts):.1f} ms')
        os.remove(jp); os.remove(op)


if __name__ == '__main__':
    main()
