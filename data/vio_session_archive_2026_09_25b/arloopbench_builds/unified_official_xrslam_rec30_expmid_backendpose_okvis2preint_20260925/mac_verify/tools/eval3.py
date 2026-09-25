#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[bkpose 2026-09-25] 三种 XRSLAM 位姿对 ARKit 的尺度 / ATE / 5 s 分段尺度(只读评分)。
键控:录制整数纳秒 t_ns 精确相等(前端 = keyed.csv;后端 = backend.csv 的 t_ns 列,由回放器按喂入时间
逐位反查),ARKit 用 lidar_ruler.arkit_poses(去零平移、只留 arkit_tracking==normal、0.5 ms 内对帧)。
估计量:scale_eval.estimators(09-24 真值审计规范估计器,Umeyama Sim3 前向 k = 1/s,ATE_sim3)。
5 s 分段:把共同帧按 t 切成不重叠 5 s 窗,每窗单独 Sim3 得 k_w,报 k_w / k_全场 − 1。
用法:eval3.py <tag> <scene> <recording dir>
"""
import csv, json, sys
import numpy as np
LR_DIR = '/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler'
sys.path.insert(0, LR_DIR)
import lidar_ruler as LR  # noqa: E402
SE = LR._load_scale_eval()
W = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint/runs/'

def _R(r):
    return LR.quat_to_rmat(float(r['qx']), float(r['qy']), float(r['qz']), float(r['qw']))

def load_keyed(p):
    return {int(r['t_ns']): (_R(r), np.array([float(r['tx']), float(r['ty']), float(r['tz'])])) for r in csv.DictReader(open(p))}

def load_backend(p):
    first, final, window = {}, {}, {}
    for r in csv.DictReader(open(p)):
        t = int(r['t_ns'])
        if t < 0:
            continue
        c = (_R(r), np.array([float(r['tx']), float(r['ty']), float(r['tz'])]))
        if r['kind'] == '1':
            first.setdefault(t, c)
        elif r['kind'] == '2':
            final[t] = c          # 同一帧只会离窗一次;若有重复取最后一次
        elif r['kind'] == '3':
            window[t] = c
    fin = dict(window); fin.update(final)   # 定稿 = Final;收尾时仍在窗口的帧取最后一次窗口快照
    return first, fin, final, window

def windows_k(t, X, Y, kg, win=5.0, min_n=10):
    out = []
    t0 = t[0]
    nw = int(np.floor((t[-1] - t0) / win)) + 1
    for i in range(nw):
        m = (t >= t0 + i * win) & (t < t0 + (i + 1) * win)
        if m.sum() < min_n:
            continue
        s, _, _, _ = SE['sim3'](X[:, m], Y[:, m])
        out.append((float(t0 + i * win - t[0]), int(m.sum()), (1.0 / s) / kg - 1.0))
    return out

def metrics(est, ark, min_n):
    ts = sorted(set(est) & set(ark))
    X = np.array([est[t][1] for t in ts]).T
    Y = np.array([ark[t][1] for t in ts]).T
    t = np.array(ts) * 1e-9
    r = SE['estimators'](X, Y)
    wk = windows_k(t, X, Y, r['k_sim3_fwd'], 5.0, min_n)
    e = np.array([w[2] for w in wk])
    # 相邻共同帧之间的相对旋转对 ARKit 的误差(相机系,与两边的世界系无关)
    rr = []
    for a, b in zip(ts[:-1], ts[1:]):
        if (b - a) * 1e-9 > 0.2:
            continue
        Re = est[a][0].T @ est[b][0]; Ra = ark[a][0].T @ ark[b][0]
        c = (np.trace(Ra.T @ Re) - 1) / 2
        rr.append(np.degrees(np.arccos(np.clip(c, -1, 1))))
    rr = np.array(rr)
    return {'n': len(ts), 'k': r['k_sim3_fwd'], 'ate_cm': r['ate_sim3_cm'],
            'rel_rot_err_deg_med': float(np.median(rr)), 'rel_rot_err_deg_p95': float(np.percentile(rr, 95)), 'rel_rot_pairs': len(rr),
            'seg5': [[round(a, 1), n, round(100 * d, 2)] for a, n, d in wk],
            'seg5_min_pct': float(100 * e.min()), 'seg5_max_pct': float(100 * e.max()),
            'seg5_sd_pct': float(100 * e.std()), 'seg5_n': len(wk)}

if __name__ == '__main__':
    tag, scene, rec = sys.argv[1], sys.argv[2], sys.argv[3]
    frame_ts = [int(l.split(',')[0]) for l in open(rec + '/camera_index.csv').read().split('\n')[1:] if l]
    ark, st = LR.arkit_poses(rec, rec + '/arkit_poses.tum', frame_ts)
    front = load_keyed(W + tag + '.keyed.csv')
    first, fin, final, window = load_backend(W + tag + '.backend.csv')
    bset = set(first)
    front_at_b = {t: c for t, c in front.items() if t in bset}
    res = {'tag': tag, 'scene': scene, 'arkit': {'frames': len(ark), **st},
           'counts': {'front': len(front), 'backend_first': len(first), 'backend_final_any': len(fin),
                      'backend_final_marginalized': len(final), 'backend_final_window_only': len(set(window) - set(final))}}
    for name, est, mn in (('front', front, 30), ('front@backend_frames', front_at_b, 10),
                          ('backend_first', first, 10), ('backend_final', fin, 10)):
        res[name] = metrics(est, ark, mn)
    json.dump(res, open(W + tag + '.eval3.json', 'w'), indent=1, ensure_ascii=False)
    print(f"{scene} ARKit 可用帧 {len(ark)};计数 {res['counts']}")
    for name in ('front', 'front@backend_frames', 'backend_first', 'backend_final'):
        m = res[name]
        print(f"  {name:22s} n={m['n']:4d} k={m['k']:.4f} ({100*(m['k']-1):+.2f}%) ATE={m['ate_cm']:.2f} cm "
              f"5s分段 {m['seg5_min_pct']:+.1f}…{m['seg5_max_pct']:+.1f}% sd {m['seg5_sd_pct']:.1f}% ({m['seg5_n']}窗) "
              f"相邻帧相对旋转误差 中位 {m['rel_rot_err_deg_med']:.3f}° p95 {m['rel_rot_err_deg_p95']:.3f}° ({m['rel_rot_pairs']}对)")
