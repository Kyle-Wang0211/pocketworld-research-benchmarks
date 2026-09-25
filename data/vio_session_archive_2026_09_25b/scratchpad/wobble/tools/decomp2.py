#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""尺子逐帧对:API 预测位姿 vs 后端 kf_final 插值位姿(同一组帧对/匹配/深度)。"""
import argparse, os, sys
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
from decomp import LR, xr_mac_poses
import wob
from kfinterp import interp_to

ap = argparse.ArgumentParser(); ap.add_argument('scene'); ap.add_argument('tag'); ap.add_argument('--pairs', type=int, default=400)
a = ap.parse_args()
args = argparse.Namespace(detector='sift', features=4000, ratio=0.8, pairs=a.pairs, pair_dt=0.5, depth_tol_ms=0.5, min_points=20,
                          min_pairs=8, min_baseline=0.02, max_reproj_px=2.0, min_angle_deg=1.0, min_confidence=LR.DR.CONF_HIGH,
                          max_between=0.15, max_within=0.25, seed=20260924)
rec = wob.rdir(a.scene) + '/ruler_subset'
scene = LR.Scene(rec, args); frame_ts = [t for t, _ in scene.ts]
ark, _ = LR.arkit_poses(rec, os.path.join(rec, 'arkit_poses.tum'), frame_ts)
T = {'arkit': ark, 'api': xr_mac_poses(a.tag, frame_ts), 'kf_interp': interp_to(a.scene, a.tag, frame_ts),
     'latest_interp': interp_to(a.scene, a.tag, frame_ts, 'latest')}
usable = [f for f in scene.frames if all(f['t_ns'] in tj for tj in T.values())]
pairs = scene.select_pairs(usable)
res = {k: [] for k in T}
for fa, fb in pairs:
    pa, pb = scene.matches(fa, fb); d = scene.depth_of(fa)
    for k, tj in T.items():
        m = LR.pair_measure(scene, fa, fb, pa, pb, tj[fa['t_ns']], tj[fb['t_ns']], d, args)
        res[k].append(1 / m['scale_to_metric'] if 'scale_to_metric' in m else np.nan)
R = {k: np.array(v) for k, v in res.items()}
ok = np.all([np.isfinite(v) for v in R.values()], 0)
print('%s %s 帧对 %d 共同有效 %d' % (a.scene, a.tag, len(pairs), ok.sum()))
for k, v in R.items():
    q = v[ok] / (R['arkit'][ok] if k != 'arkit' else 1)
    seg = [np.median(x) for x in np.array_split(v[ok], 4)]
    print('  %-14s k 中位 %.4f | 对 ARKit 逐对比 IQR %.4f 稳健sd %.4f | 分段(对 LiDAR) %s  极差 %.1f%%' % (
        k, np.median(v[ok]), np.subtract(*np.percentile(q, [75, 25])), 1.4826 * np.median(np.abs(q - np.median(q))),
        ' '.join('%.3f' % s for s in seg), 100 * (max(seg) - min(seg)) / np.median(seg)))
