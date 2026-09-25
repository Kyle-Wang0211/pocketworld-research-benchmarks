#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 初始化 / 跟踪 / 关键帧决策的逐帧对比(诊断,只读 PW_DIAG_LOG)。
日志行:FT id t 上一帧点数 跟上点数 无平移标记 前端预测转角(rad);SW id t 是否关键帧 三角化点数 评估数 RPE 剔除 深度剔除;
INIT 首帧t 末帧t 帧数 尺度 重力(SfM 系 3) bg(3) ba(3)。
另从后端 CSV 取初始化窗首帧的 body 姿态,算 body 系重力方向,与 ARKit 同帧的重力方向比(两边各自对 ARKit)。
用法:trackdiff.py <scene> <tagA> <tagB>"""
import csv
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
sys.path.insert(0, SP + '/wobble/tools')
import eval3  # noqa: E402
import preint_eval as PE  # noqa: E402
import wob  # noqa: E402

LOG = SP + '/preint/runs/diaglog/'


def load(tag):
    ft, sw, init = {}, {}, None
    for ln in open(LOG + tag + '.log'):
        a = ln.split()
        if a[0] == 'FT':
            ft[int(a[1])] = (float(a[2]), int(a[3]), int(a[4]), int(a[5]), float(a[6]))
        elif a[0] == 'SW':
            sw[int(a[1])] = (float(a[2]), int(a[3]), int(a[4]), int(a[5]), int(a[6]), int(a[7]))
        elif a[0] == 'INIT':
            v = [float(x) for x in a[1:]]
            init = dict(t0=v[0], t1=v[1], n=int(v[2]), scale=v[3], g=np.array(v[4:7]), bg=np.array(v[7:10]), ba=np.array(v[10:13]))
    return ft, sw, init


def init_gravity(tag, sc):
    """初始化窗第一帧(最早的 First 事件)的 body 系重力方向 vs ARKit 同帧相机系重力方向 → 经外参换到 body 系比较。"""
    rows = [r for r in csv.DictReader(open(PE.W + tag + '.backend.csv')) if r['kind'] == '1' and int(r['t_ns']) > 0]
    r0 = min(rows, key=lambda r: float(r['engine_t']))
    qb = np.array([float(r0['body_q' + c]) for c in 'xyzw'])
    Rwb = wob.qmat(qb[None])[0]
    g_b = Rwb.T @ np.array([0, 0, -1.0])
    A = wob.load_arkit(sc)
    i = int(np.nonzero(A['tns'] == int(r0['t_ns']))[0][0])
    Rwc = wob.qmat(A['Q'][i:i + 1])[0] @ PE.D   # ARKit 相机(转 OpenCV 轴)在 ARKit 世界(y 向上)
    g_c = Rwc.T @ np.array([0, -1.0, 0])
    Rbc, _ = PE.__dict__.get('yaml_ext', None) or (None, None) if False else (None, None)
    return g_b, g_c, int(r0['t_ns'])


def main(sc, ta, tb):
    fa, sa, ia = load(ta)
    fb, sb, ib = load(tb)
    print('== %s  %s vs %s' % (sc, ta, tb))
    if ia and ib:
        print('  初始化:窗 [%.3f, %.3f] s 帧数 %d | %d;同一批帧 %s' % (ia['t0'] - ia['t0'], ia['t1'] - ia['t0'], ia['n'], ib['n'],
                                                        ia['t0'] == ib['t0'] and ia['t1'] == ib['t1']))
        print('  初始尺度 %.5f → %.5f(%+.2f%%);重力(SfM 系)夹角 %.3f°;bg %s → %s(差 %.2e rad/s)' % (
            ia['scale'], ib['scale'], 100 * (ib['scale'] / ia['scale'] - 1),
            np.degrees(np.arccos(np.clip(ia['g'] @ ib['g'] / np.linalg.norm(ia['g']) / np.linalg.norm(ib['g']), -1, 1))),
            np.round(ia['bg'], 5), np.round(ib['bg'], 5), np.linalg.norm(ia['bg'] - ib['bg'])))
    # 跟踪逐帧
    ids = sorted(set(fa) & set(fb))
    da = np.array([fa[i][2] for i in ids]); db = np.array([fb[i][2] for i in ids])
    diff = np.nonzero(da != db)[0]
    first = ids[diff[0]] if len(diff) else None
    print('  前端跟踪:共同帧 %d;跟上点数第一次不同在帧 %s(%.2f s);此后不同的帧占 %.0f%%;跟上点数均值 %.1f vs %.1f;跟踪率 %.3f vs %.3f' % (
        len(ids), first, (fa[first][0] - fa[ids[0]][0]) if first else float('nan'), 100 * len(diff) / len(ids),
        da.mean(), db.mean(), np.mean([fa[i][2] / max(fa[i][1], 1) for i in ids]), np.mean([fb[i][2] / max(fb[i][1], 1) for i in ids])))
    ra = np.array([fa[i][4] for i in ids]); rb = np.array([fb[i][4] for i in ids])
    print('  前端预测转角(帧间,°):均值 %.4f vs %.4f,逐帧差 RMS %.4f°;无平移标记 %d vs %d 帧' % (
        np.degrees(ra.mean()), np.degrees(rb.mean()), np.degrees(np.sqrt(np.mean((ra - rb) ** 2))),
        sum(fa[i][3] for i in ids), sum(fb[i][3] for i in ids)))
    sids = sorted(set(sa) & set(sb))
    ka = [sa[i][1] for i in sids]; kb = [sb[i][1] for i in sids]
    kd = [i for i, x, y in zip(sids, ka, kb) if x != y]
    print('  后端:共同帧 %d;关键帧 %d vs %d;决策不同 %d 帧(第一次在帧 %s);三角化点均值 %.1f vs %.1f;RPE 剔除合计 %d vs %d;深度剔除 %d vs %d' % (
        len(sids), sum(ka), sum(kb), len(kd), kd[0] if kd else None, np.mean([sa[i][2] for i in sids]), np.mean([sb[i][2] for i in sids]),
        sum(sa[i][4] for i in sids), sum(sb[i][4] for i in sids), sum(sa[i][5] for i in sids), sum(sb[i][5] for i in sids)))


if __name__ == '__main__':
    main(*sys.argv[1:4])
