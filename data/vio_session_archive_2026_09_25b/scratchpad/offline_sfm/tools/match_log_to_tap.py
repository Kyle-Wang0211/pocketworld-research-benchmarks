#!/usr/bin/python3
# -*- coding: utf-8 -*-
"""[offline_sfm 2026-09-25 外推轮] 核对 wobble 插桩日志 <scene>_log_r1.jsonl 与 bkpose <scene>_tap_r1.backend.csv
是不是同一条轨迹(只读)。
  kf_final(边缘化时的定稿状态:p q pc v bg ba)  ↔  backend.csv kind 2(定稿,相机中心 tx..tz / body 位姿)
  latest(每次后端 track 后的最新状态:p q v ba bg)↔  backend.csv kind 1 首条(首次后端估计的 body 位姿)
按引擎时间 t 精确到 1e-9 s 配对,比较位置差(日志按 %.9g 打印)。"""
import csv, json, sys
import numpy as np
SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
MV = '/Users/kaidongwang/Developer/arloopbench_builds/unified_official_xrslam_rec30_expmid_backendpose_20260925/mac_verify'
for scene in sys.argv[1:]:
    kf, lat = {}, {}
    for l in open(f'{SP}/wobble/runs/{scene}_log_r1.jsonl'):
        if '"kf_final"' in l:
            d = json.loads(l); kf[round(d['t'], 6)] = d
        elif '"ev":"latest"' in l:
            d = json.loads(l); lat.setdefault(round(d['t'], 6), d)
    first, final, window = {}, {}, {}
    for r in csv.DictReader(open(f'{MV}/runs/{scene}_tap_r1.backend.csv')):
        k = round(float(r['engine_t']), 6)
        if r['kind'] == '1': first.setdefault(k, r)
        elif r['kind'] == '2': final[k] = r
        elif r['kind'] == '3': window[k] = r
    def d_body(d, r):
        return max(abs(d['p'][i] - float(r['body_t' + 'xyz'[i]])) for i in range(3))
    common = sorted(set(kf) & set(final))
    e = np.array([d_body(kf[t], final[t]) for t in common])
    ec = np.array([max(abs(kf[t]['pc'][i] - float(final[t]['t' + 'xyz'[i]])) for i in range(3)) for t in common])
    cf = sorted(set(lat) & set(first))
    el = np.array([d_body(lat[t], first[t]) for t in cf])
    print(f'{scene}: kf_final {len(kf)} 条,后端定稿 {len(final)} 条(另收尾窗口 {len(set(window)-set(final))}),共同 {len(common)};'
          f' body 位置最大差 {e.max():.2e} m,相机中心最大差 {ec.max():.2e} m | latest {len(lat)} 条,后端首次 {len(first)},共同 {len(cf)},最大差 {el.max():.2e} m')
    only_final = sorted(set(final) - set(kf))
    print(f'   有后端定稿但日志没有 kf_final 的帧 {len(only_final)}:', only_final[:12])
    print(f'   有 kf_final 但后端 CSV 没有定稿的帧 {len(set(kf)-set(final))}')
