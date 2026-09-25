#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计用:LiDAR 米尺逐点原始数据导出(只读,不改尺子)。
直接 import 米尺本体(lidar_ruler.py + vendored/depth_ruler.py)的同一批函数:Scene / arkit_poses /
DR.triangulate_pair / DR.reproject / DR.sample_depth,只是把每个帧对、每个匹配点的中间量都存下来,
好在事后换过滤条件、分箱、bootstrap,而不用重跑 SIFT。
输入:full_<sc>/(主录制 897 帧 luma + ruler_subset 的 296 张深度,均为符号链接)。
用法:lidar_extract.py <sc> [dt1,dt2,...]"""
import os
import sys
import types

import numpy as np

LRDIR = os.path.expanduser('~/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler')
sys.path.insert(0, LRDIR)
sys.dont_write_bytecode = True
import lidar_ruler as LR  # noqa: E402
DR = LR.DR
RA = os.path.dirname(os.path.abspath(__file__))


def main(sc, dts):
    rec = os.path.join(RA, 'full_' + sc)
    args = types.SimpleNamespace(detector='sift', features=4000, ratio=0.8, pairs=10 ** 6, pair_dt=0.5,
                                 depth_tol_ms=0.5, min_points=20, min_baseline=0.02, max_reproj_px=2.0,
                                 min_angle_deg=1.0, min_confidence=2)
    scene = LR.Scene(rec, args)
    frame_ts = [t for t, _ in scene.ts]
    ark, st = LR.arkit_poses(rec, os.path.join(rec, 'arkit_poses.tum'), frame_ts)
    usable = [f for f in scene.frames if f['t_ns'] in ark]
    print(sc, '深度帧', len(scene.frames), '有 ARKit 位姿', len(usable), st, flush=True)
    rows = []          # 每点一行
    prs = []           # 每对一行
    seen = set()
    for dt in dts:
        args.pair_dt = dt
        for fa, fb in scene.select_pairs(usable):
            key = (fa['t_ns'], fb['t_ns'])
            if key in seen:
                continue
            seen.add(key)
            pa, pb = scene.matches(fa, fb)
            pid = len(prs)
            Ka = np.array([[fa['K'][0], 0, fa['K'][2]], [0, fa['K'][1], fa['K'][3]], [0, 0, 1.0]])
            Kb = np.array([[fb['K'][0], 0, fb['K'][2]], [0, fb['K'][1], fb['K'][3]], [0, 0, 1.0]])
            R_rel, t_rel = LR.rel_pose(ark[fa['t_ns']], ark[fb['t_ns']])
            base = float(np.linalg.norm(t_rel))
            rot = float(np.degrees(np.arccos(np.clip((np.trace(R_rel) - 1) / 2, -1, 1))))
            prs.append([pid, fa['t_ns'] * 1e-9, fb['t_ns'] * 1e-9, base, rot, fa['K'][0], fb['K'][0], len(pa)])
            if len(pa) < 8 or base < 1e-4:
                continue
            X, P_a, P_b = DR.triangulate_pair(Ka, Kb, R_rel, t_rel, pa, pb)
            z_a = X[:, 2]
            X_b = (R_rel @ X.T).T + t_rel
            e_a = np.linalg.norm(DR.reproject(P_a, X) - pa, axis=1)
            e_b = np.linalg.norm(DR.reproject(P_b, X) - pb, axis=1)
            C_b_in_a = -R_rel.T @ t_rel
            v1, v2 = X, X - C_b_in_a
            with np.errstate(invalid='ignore', divide='ignore'):
                cosang = np.sum(v1 * v2, 1) / (np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1))
            ang = np.degrees(np.arccos(np.clip(cosang, -1, 1)))
            dmap, cmap = scene.depth_of(fa)
            d_l, conf, ok0 = DR.sample_depth(dmap, cmap, pa, (scene.W, scene.H), 0)
            # 双线性取深度(诊断用,尺子本体是最近邻)
            H_d, W_d = dmap.shape
            u = (pa[:, 0] + 0.5) * W_d / scene.W - 0.5
            v = (pa[:, 1] + 0.5) * H_d / scene.H - 0.5
            u0 = np.clip(np.floor(u).astype(int), 0, W_d - 2); v0 = np.clip(np.floor(v).astype(int), 0, H_d - 2)
            au = np.clip(u - u0, 0, 1); av = np.clip(v - v0, 0, 1)
            d_bil = (dmap[v0, u0] * (1 - au) * (1 - av) + dmap[v0, u0 + 1] * au * (1 - av)
                     + dmap[v0 + 1, u0] * (1 - au) * av + dmap[v0 + 1, u0 + 1] * au * av)
            # 3×3 邻域深度极差(边缘/混合像素诊断)
            iu = np.clip(np.rint(u).astype(int), 1, W_d - 2); iv = np.clip(np.rint(v).astype(int), 1, H_d - 2)
            nb = np.stack([dmap[iv + a, iu + b] for a in (-1, 0, 1) for b in (-1, 0, 1)], 1)
            d_rng = nb.max(1) - nb.min(1)
            # 深度图下一行(时间上 +1 张深度 = +3 帧 = +0.1 s)同像素,诊断时间对齐
            for i in range(len(pa)):
                rows.append([pid, pa[i, 0], pa[i, 1], pb[i, 0], pb[i, 1], z_a[i], X_b[i, 2], e_a[i], e_b[i], ang[i],
                             d_l[i], conf[i], d_bil[i], d_rng[i]])
        print(sc, 'dt', dt, '累计帧对', len(prs), '点', len(rows), flush=True)
    out = os.path.join(RA, 'pts_%s.npz' % sc)
    np.savez_compressed(out, pts=np.array(rows, dtype=np.float64), pairs=np.array(prs, dtype=np.float64),
                        cols_pts='pid ua va ub vb z_tri zb_tri e_a e_b ang_deg d_nn conf d_bil d_rng3x3',
                        cols_pairs='pid t_a t_b baseline_traj rot_deg fx_a fx_b n_match')
    print('写出', out)


if __name__ == '__main__':
    sc = sys.argv[1]
    dts = [float(x) for x in (sys.argv[2] if len(sys.argv) > 2 else '0.2,0.3,0.4,0.6,0.9').split(',')]
    main(sc, dts)
