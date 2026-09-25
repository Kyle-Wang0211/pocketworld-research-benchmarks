#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 汇总:任务一改前改后大表 + 任务二同口径倍数与抖动来源。只读已落盘的回放。"""
import json
import os
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
import preint_eval as PE  # noqa: E402
import rs_bins as RS  # noqa: E402

SC = ['13f5', '6d18', '7353']
OUT = SP + '/preint/stats/'
cache = {}


def ev(sc, tag):
    if (sc, tag) not in cache:
        cache[(sc, tag)] = (PE.run(sc, tag), RS.run(sc, tag))
    return cache[(sc, tag)]


def main():
    lines = []
    P = lines.append
    P('## 任务一:改前(8ebac9a 左端零阶保持)vs 改后(OKVIS2 离散),Mac 单线程回放(逐位可复现)')
    P('场 | 位姿 | 版本 | 陀螺偏移 s(相对引擎时间戳) | 幅度比 g | 每增量旋转抖动 RMS | 对 ARKit 尺度 | 链式对 LiDAR | ATE | 5 s 分段 min…max(sd) | 2 s 窗尺度 sd(max) ')
    for sc in SC:
        for name, lab in (('front', '前端'), ('backend_first', '后端首次'), ('backend_final', '后端定稿')):
            for v, vl in (('base', '改前'), ('okvis', '改后')):
                r = ev(sc, '%s_%s_nothr_r1' % (sc, v))[0]['rows'][name]
                P('%s | %s | %s | %+.2f ms | %.4f | %.4f° | %+.2f%% | %+.2f%% | %.2f cm | %+.1f…%+.1f%% (%.1f) | %.1f%% (%.1f) ' % (
                    sc, lab, vl, r['s_engine_ms'], r['g'], r['jitter_deg'], 100 * (r['k_ark'] - 1),
                    100 * (r['k_lidar'] - 1), r['ate_cm'], r['seg5_min'], r['seg5_max'], r['seg5_sd'], r['win2_sd'],
                    r['win2_absmax']))
    P('')
    P('## 线程化(手机同配置)核对:改后 vs 改前')
    for sc in SC:
        for name, lab in (('front', '前端'), ('backend_first', '后端首次'), ('backend_final', '后端定稿')):
            cells = []
            for v in ('base', 'okvis'):
                r = ev(sc, '%s_%s_thr_r1' % (sc, v))[0]['rows'][name]
                cells.append('s %+.2f ms 抖动 %.4f° k_LiDAR %+.2f%% ATE %.2f cm' % (
                    r['s_engine_ms'], r['jitter_deg'], 100 * (r['k_lidar'] - 1), r['ate_cm']))
            P('%s %s | 改前 %s | 改后 %s' % (sc, lab, cells[0], cells[1]))
    P('')
    P('## 任务二 第 0 步:同口径(都只取后端帧、100 ms 增量)')
    P('场 | ARKit 全帧 33 ms RMS(旧口径) | ARKit@后端帧 RMS / 中位 | 后端定稿 改前 RMS / 中位 | 倍数(RMS / 中位) | 后端定稿 改后 RMS / 中位 | 倍数(RMS / 中位)')
    for sc in SC:
        pb, rb = ev(sc, '%s_base_nothr_r1' % sc)
        po, ro = ev(sc, '%s_okvis_nothr_r1' % sc)
        a33 = pb['rows']['arkit_all']['jitter_deg']
        ab = rb['arkit@backend']
        b = rb['backend_final']
        o = ro['backend_final']
        P('%s | %.4f° | %.4f° / %.4f° | %.4f° / %.4f° | %.2f× / %.2f× | %.4f° / %.4f° | %.2f× / %.2f×' % (
            sc, a33, ab['rms'], ab['med'], b['rms'], b['med'], b['rms'] / ab['rms'], b['med'] / ab['med'],
            o['rms'], o['med'], o['rms'] / ab['rms'], o['med'] / ab['med']))
        P('%s 旧口径倍数(后端定稿 100 ms RMS ÷ ARKit 33 ms RMS):改前 %.2f×,改后 %.2f×' % (
            sc, b['rms'] / a33, o['rms'] / a33))
    P('')
    P('## 任务二 第 1 步:改后引擎上逐项对照(后端定稿,单线程)')
    arms = [('ref', '%s_okvis_nothr_r1', '改后引擎(参照)'), ('qark', '%s_okvis_nothr_qark', '外参换 ARKit 隐含值'),
            ('win10', '%s_okvis_nothr_win10', '滑窗 5→10'), ('tdm25', '%s_okvis_nothr_tdm25', 'td −2.5 ms(诊断)'),
            ('tdm5', '%s_okvis_nothr_tdm5', 'td −5 ms(诊断)')]
    agg = {a[0]: {'rms': [], 'med': []} for a in arms}
    for sc in SC:
        ref = None
        for key, pat, lab in arms:
            tag = pat % sc
            if not os.path.exists(PE.W + tag + '.backend.csv'):
                P('%s %s 缺回放' % (sc, lab))
                continue
            p, r = ev(sc, tag)
            b = r['backend_final']
            f = p['rows']['backend_final']
            if key == 'ref':
                ref = b
            agg[key]['rms'].append(b['rms'])
            agg[key]['med'].append(b['med'])
            P('%s | %-18s | RMS %.4f° (%+.1f%%) 中位 %.4f° (%+.1f%%) | 残差≈%.4f°+%.4f°/(rad/s)·ω r=%.2f | s %+.2f ms | k_LiDAR %+.2f%% ATE %.2f cm 5s sd %.1f%%' % (
                sc, lab, b['rms'], 100 * (b['rms'] / ref['rms'] - 1), b['med'], 100 * (b['med'] / ref['med'] - 1),
                b['a_deg'], b['b_deg_per_rads'], b['pearson'], f['s_engine_ms'], 100 * (f['k_lidar'] - 1), f['ate_cm'],
                f['seg5_sd']))
    P('三场平均(RMS / 中位)相对参照:')
    for key, pat, lab in arms:
        if len(agg[key]['rms']) == 3:
            P('  %-18s RMS %.4f° (%+.1f%%)  中位 %.4f° (%+.1f%%)' % (
                lab, np.mean(agg[key]['rms']), 100 * (np.mean(agg[key]['rms']) / np.mean(agg['ref']['rms']) - 1),
                np.mean(agg[key]['med']), 100 * (np.mean(agg[key]['med']) / np.mean(agg['ref']['med']) - 1)))
    P('')
    P('## 卷帘快门:后端定稿逐增量残差按角速度分箱(改后引擎)vs 同批帧 ARKit')
    for sc in SC:
        r = ev(sc, '%s_okvis_nothr_r1' % sc)[1]
        for name in ('backend_final', 'arkit@backend'):
            d = r[name]
            cells = '  '.join('[%.1f,%.1f) n%d %s' % (a, b, n, '%.3f°' % v if v is not None else '—') for a, b, n, v in d['bins'])
            P('%s %-14s 斜率 %.4f°/(rad/s) 截距 %.4f° r=%.2f | %s' % (sc, name, d['b_deg_per_rads'], d['a_deg'], d['pearson'], cells))
    txt = '\n'.join(lines)
    open(OUT + 'summary.txt', 'w').write(txt)
    json.dump({'%s|%s' % k: v for k, v in cache.items()}, open(OUT + 'summary.json', 'w'), indent=1, ensure_ascii=False,
              default=float)
    print(txt)


if __name__ == '__main__':
    main()
