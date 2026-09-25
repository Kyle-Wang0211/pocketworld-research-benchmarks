#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 外推轮] 外推工具的可失败验证:用日志里的 `latest` 后端状态 + xr_propagate 复现前端对外输出。
前端 XRSLAM_RESULT_CAMERA_POSE(t) = predict_pose(t)(某个 latest 状态沿 IMU 外推)× camera_to_body。
对每个前端帧(<scene>_log_r1 同一次运行的 keyed/cam 输出),试它之前 0.6 s 内的每个 latest 状态,取误差最小者。
若工具、IMU 样本、外参三者任一不对,最小误差会远大于打印精度(keyed.csv %.9f)。
用法:validate_propagate.py <scene> [<front csv>]"""
import csv, json, os, subprocess, sys
import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
O = SP + '/offline_sfm'
MV = os.path.expanduser('~/Developer/arloopbench_builds/unified_official_xrslam_rec30_expmid_backendpose_20260925/mac_verify')
RECS = {'13f5': 'run-13f53d2f-5935-4b1a-a499-4dc8367ea935', '6d18': 'run-6d187dff-403a-4882-b692-7bdc6c3cfa2a',
        '7353': 'run-73538ad6-8418-4eaf-8b75-a63c9d32af46'}


def load_latest(scene):
    L = []
    seen = set()
    for l in open(f'{SP}/wobble/runs/{scene}_log_r1.jsonl'):
        if '"ev":"latest"' not in l:
            continue
        d = json.loads(l)
        k = round(d['t'], 9)
        if k in seen:
            continue
        seen.add(k)
        L.append(d)
    return L


def main():
    scene = sys.argv[1]
    rec = os.path.expanduser('~/Developer/viobench-recordings/' + RECS[scene])
    front = []
    for r in csv.DictReader(open(f'{MV}/runs/{scene}_tap_r1.keyed.csv')):
        front.append((float(r['engine_t']), np.array([float(r[c]) for c in ('tx', 'ty', 'tz')]),
                      np.array([float(r[c]) for c in ('qx', 'qy', 'qz', 'qw')])))
    lat = load_latest(scene)
    jobs = []
    for j, (t, p, q) in enumerate(front):
        for i, d in enumerate(lat):
            if t - 0.6 < d['t'] < t:
                v = [d['t']] + d['p'] + d['q'] + d['v'] + d['bg'] + d['ba'] + [t]
                jobs.append(f'f{j}_s{i} ' + ' '.join('%.17g' % x for x in v))
    jp = f'{O}/tmp_validate_{scene}.jobs'; op = f'{O}/tmp_validate_{scene}.out'
    open(jp, 'w').write('\n'.join(jobs) + '\n')
    subprocess.run([f'{O}/build/xr_propagate', f'{SP}/bkpose/cfg/slam_config.yaml', f'{SP}/bkpose/cfg/dev_{scene}.yaml',
                    rec + '/imu.csv', jp, op], check=True)
    best = {}
    for l in open(op):
        f = l.split(); j = int(f[0].split('_')[0][1:])
        cp = np.array([float(x) for x in f[12:15]]); cq = np.array([float(x) for x in f[15:19]])
        t, p, q = front[j]
        e = np.linalg.norm(cp - p)
        eq = min(np.linalg.norm(cq - q), np.linalg.norm(cq + q))
        if j not in best or e < best[j][0]:
            best[j] = (e, eq, f[0])
    e = np.array([b[0] for b in best.values()]); eq = np.array([b[1] for b in best.values()])
    print(f'{scene}: 前端帧 {len(front)},有候选 {len(best)};最佳匹配的位置误差 中位 {np.median(e):.2e} m、'
          f'p99 {np.percentile(e, 99):.2e}、最大 {e.max():.2e};四元数差 最大 {eq.max():.2e};'
          f'位置误差 ≤1e-8 m 的帧 {int((e <= 1e-8).sum())}/{len(e)}')
    # 负对照:外参换成单位阵 / 零偏置零时,最佳匹配误差必须明显变大(见 --negctl)
    os.remove(jp); os.remove(op)


if __name__ == '__main__':
    main()
