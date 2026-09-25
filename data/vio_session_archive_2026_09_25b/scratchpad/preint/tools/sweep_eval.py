#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] td 扫描评分(只读):两个引擎 × Δ(−10…+4 ms)× 三场,每格前端 / 后端定稿两行。
指标全部复用 preint_eval.run(k、LiDAR 链式、ATE、5 s 分段、2 s 窗、陀螺偏移)与 rs_bins.run(同口径抖动)。
输出 stats/sweep.json(全量)+ stats/sweep_table.tsv(大表)+ 屏幕摘要(各判据的最优 Δ)。"""
import json
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
import preint_eval as PE  # noqa: E402
import rs_bins as RS  # noqa: E402

OUT = SP + '/preint/stats/'
SC = ['13f5', '6d18', '7353']
DS = list(range(-10, 9))
ENG = {'base': '改前 8ebac9a', 'okvis': '改后 bdf9080'}


def tag(sc, e, d):
    return '%s_%s_nothr_sw%s' % (sc, e, ('m%d' % -d) if d < 0 else ('p%d' % d))


def collect():
    rows = []
    for e in ENG:
        for d in DS:
            for sc in SC:
                t = tag(sc, e, d)
                p = PE.run(sc, t)
                r = RS.run(sc, t)
                for name in ('backend_final', 'front'):
                    x = p['rows'][name]
                    j = r['backend_final'] if name == 'backend_final' else None
                    rows.append(dict(engine=e, delta_ms=d, scene=sc, pose=name, s_engine_ms=x['s_engine_ms'],
                                     s_pts_ms=x['s_pts_ms'], g=x['g'], jitter_deg=x['jitter_deg'],
                                     k_ark_pct=100 * (x['k_ark'] - 1), k_lidar_pct=100 * (x['k_lidar'] - 1),
                                     ate_cm=x['ate_cm'], seg5_min=x['seg5_min'], seg5_max=x['seg5_max'],
                                     seg5_sd=x['seg5_sd'], win2_sd=x['win2_sd'], win2_absmax=x['win2_absmax'],
                                     same_rms_deg=j['rms'] if j else None, same_med_deg=j['med'] if j else None,
                                     ark_same_rms_deg=r['arkit@backend']['rms'] if j else p['rows']['arkit_all']['jitter_deg'],
                                     ark_same_med_deg=r['arkit@backend']['med'] if j else None, n=x['n']))
                print('.', end='', flush=True)
    print()
    return rows


def main():
    rows = collect()
    json.dump(rows, open(OUT + 'sweep.json', 'w'), indent=1, ensure_ascii=False)
    cols = ['engine', 'delta_ms', 'scene', 'pose', 'k_ark_pct', 'k_lidar_pct', 'ate_cm', 'seg5_min', 'seg5_max', 'seg5_sd',
            'win2_sd', 'win2_absmax', 'jitter_deg', 'same_rms_deg', 'same_med_deg', 'ark_same_rms_deg', 'ark_same_med_deg',
            's_engine_ms', 's_pts_ms', 'g', 'n']
    with open(OUT + 'sweep_table.tsv', 'w') as f:
        f.write('\t'.join(cols) + '\n')
        for r in rows:
            f.write('\t'.join('' if r[c] is None else (('%.4f' % r[c]) if isinstance(r[c], float) else str(r[c])) for c in cols) + '\n')
    print('写出', OUT + 'sweep.json', OUT + 'sweep_table.tsv', len(rows), '行')


if __name__ == '__main__':
    main()
