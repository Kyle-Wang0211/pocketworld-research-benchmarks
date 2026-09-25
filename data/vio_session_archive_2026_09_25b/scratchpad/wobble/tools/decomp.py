#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐帧对分解:LiDAR 尺子给 XRSLAM 的逐帧对尺度偏差,来自基线长度 / 基线方向 / 相对旋转中的哪一项?
复用 lidar_ruler.py 的 Scene / pair_measure(同一组帧对、同一套匹配与深度),只换每对的两个位姿:
  ark  : ARKit 两帧位姿(参照)
  xr   : XRSLAM 两帧位姿(= 尺子原样)
  len  : ARKit 旋转 + ARKit 基线方向,基线长度换成 XR 的(再除以 XR 全局 Sim3 尺度)
  dir  : ARKit 旋转 + ARKit 基线长度,基线方向(在 a 相机系下)换成 XR 的
  rot  : ARKit 两个相机中心,b 的旋转换成 R_a·(XR 的相对旋转)
用法:decomp.py <scene> <xr 来源: phone | Mac 回放 tag> [--pairs N] [--pair-dt s]
"""
import argparse
import json
import os
import sys

import numpy as np

RULER = os.path.expanduser('~/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler')
sys.path.insert(0, RULER)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lidar_ruler as LR  # noqa: E402
import wob  # noqa: E402


def rot_angle_deg(R):
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))


def xr_mac_poses(tag, frame_ts):
    C = np.loadtxt(wob.W + '/runs/%s.cam.tum' % tag)
    mp = {}
    for ln in open(wob.W + '/runs/%s.map' % tag):
        a, b = ln.split()
        mp[a] = int(b)
    by_t = {}
    for r in C:
        k = '%.9f' % r[0]
        if k not in mp or np.linalg.norm(r[4:8]) < 0.5:
            continue
        by_t[mp[k]] = (LR.quat_to_rmat(*r[4:8]), r[1:4].copy())
    return {t: by_t[t] for t in frame_ts if t in by_t}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('scene')
    ap.add_argument('xr')
    ap.add_argument('--pairs', type=int, default=400)
    ap.add_argument('--pair-dt', type=float, default=0.5)
    ap.add_argument('--out')
    a = ap.parse_args()
    # 尺子默认参数(与 lidar_ruler.main 相同)
    args = argparse.Namespace(detector='sift', features=4000, ratio=0.8, pairs=a.pairs, pair_dt=a.pair_dt,
                              depth_tol_ms=0.5, min_points=20, min_pairs=8, min_baseline=0.02,
                              max_reproj_px=2.0, min_angle_deg=1.0, min_confidence=LR.DR.CONF_HIGH,
                              max_between=0.15, max_within=0.25, seed=20260924)
    rec = wob.rdir(a.scene) + '/ruler_subset'
    scene = LR.Scene(rec, args)
    frame_ts = [t for t, _ in scene.ts]
    ark, _ = LR.arkit_poses(rec, os.path.join(rec, 'arkit_poses.tum'), frame_ts)
    if a.xr == 'phone':
        xr, _ = LR.xrslam_camera_by_frame(wob.PHONE[a.scene] + '/poses_camera_by_recording_frame.csv', frame_ts)
    else:
        xr = xr_mac_poses(a.xr, frame_ts)
    # XR 全局尺度:整段 Sim3(用整条轨迹,不是子集)
    xr_full = wob.load_xr_phone(a.scene) if a.xr == 'phone' else wob.load_xr_mac(a.xr)
    J = wob.join(xr_full, wob.load_arkit(a.scene))
    kg = wob.k_sim3(J['X'], J['Y'])
    usable = [f for f in scene.frames if f['t_ns'] in ark and f['t_ns'] in xr]
    pairs = scene.select_pairs(usable)
    rows = []
    for fa, fb in pairs:
        pa, pb = scene.matches(fa, fb)
        depth = scene.depth_of(fa)
        Ra, Ca = ark[fa['t_ns']]; Rb, Cb = ark[fb['t_ns']]
        ra, ca = xr[fa['t_ns']]; rb, cb = xr[fb['t_ns']]
        dA = Cb - Ca; dX = cb - ca
        LA, LX = np.linalg.norm(dA), np.linalg.norm(dX)
        v = {
            'ark': ((Ra, Ca), (Rb, Cb)),
            'xr': ((ra, ca), (rb, cb)),
            'len': ((Ra, Ca), (Rb, Ca + dA * (LX / kg) / LA)),
            'dir': ((Ra, Ca), (Rb, Ca + Ra @ (ra.T @ dX / LX) * LA)),
            'rot': ((Ra, Ca), (Ra @ (ra.T @ rb), Cb)),
        }
        r = {'t_a': fa['t_ns'] * 1e-9, 't_b': fb['t_ns'] * 1e-9, 'len_ratio': LX / kg / LA, 'base_m': LA,
             'rot_err_deg': rot_angle_deg((Ra.T @ Rb).T @ (ra.T @ rb)),
             'dir_err_deg': float(np.degrees(np.arccos(np.clip(
                 np.dot(Ra.T @ dA / LA, ra.T @ dX / LX), -1, 1)))),
             'rel_rot_deg': rot_angle_deg(Ra.T @ Rb), 'rel_rot_xr_deg': rot_angle_deg(ra.T @ rb)}
        for name, (A, B) in v.items():
            m = LR.pair_measure(scene, fa, fb, pa, pb, A, B, depth, args)
            r['k_' + name] = 1.0 / m['scale_to_metric'] if 'scale_to_metric' in m else np.nan
            if name == 'ark' and 'triangulation_angle_deg_median' in m:
                r['tri_ang_deg'] = m['triangulation_angle_deg_median']
                r['lidar_m'] = m['median_lidar_m']
        rows.append(r)
    ok = [r for r in rows if np.isfinite(r['k_ark']) and np.isfinite(r['k_xr'])]
    print('%s %s  XR 全局 k(对 ARKit)= %.4f   帧对 %d / 有效 %d' % (a.scene, a.xr, kg, len(rows), len(ok)))
    ka = np.array([r['k_ark'] for r in ok])
    print('  ARKit 逐帧对 k(对 LiDAR):中位 %.4f  IQR/中位 %.3f' % (np.median(ka), np.subtract(*np.percentile(ka, [75, 25])) / np.median(ka)))
    for name in ('xr', 'len', 'dir', 'rot'):
        q = np.array([r['k_' + name] for r in ok]) / ka
        if name == 'xr':
            q = q / kg
        f = np.isfinite(q)
        print('  变体 %-4s 逐帧对 k/k_ark:中位 %.4f  IQR %.4f  sd(稳健 1.4826·MAD) %.4f  |偏差|>5%% 占 %.0f%%' % (
            name, np.median(q[f]), np.subtract(*np.percentile(q[f], [75, 25])),
            1.4826 * np.median(np.abs(q[f] - np.median(q[f]))), 100 * np.mean(np.abs(q[f] - 1) > 0.05)))
    e = np.array([[r['len_ratio'], r['rot_err_deg'], r['dir_err_deg'], r.get('tri_ang_deg', np.nan)] for r in ok])
    th = np.array([[r['rel_rot_deg'], r['rel_rot_xr_deg']] for r in ok]); big = th[:, 0] > 3
    if big.sum() > 3:
        print('  相对旋转幅度 XR/ARKit(ARKit 转角 >3° 的 %d 对):中位 %.4f  最小二乘斜率 %.4f' % (
            big.sum(), np.median(th[big, 1] / th[big, 0]), (th[big, 0] @ th[big, 1]) / (th[big, 0] @ th[big, 0])))
    print('  XR 误差量:基线长度比 中位 %.4f IQR %.4f;相对旋转误差 中位 %.3f° p90 %.3f°;基线方向误差 中位 %.2f° p90 %.2f°;三角化夹角中位 %.1f°' % (
        np.median(e[:, 0]), np.subtract(*np.percentile(e[:, 0], [75, 25])), np.median(e[:, 1]), np.percentile(e[:, 1], 90),
        np.median(e[:, 2]), np.percentile(e[:, 2], 90), np.nanmedian(e[:, 3])))
    # 各变体偏差对 xr 偏差的解释度(R²)
    qx = np.array([r['k_xr'] for r in ok]) / ka / kg
    for name in ('len', 'dir', 'rot'):
        q = np.array([r['k_' + name] for r in ok]) / ka
        f = np.isfinite(q) & np.isfinite(qx)
        c = np.corrcoef(np.log(q[f]), np.log(qx[f]))[0, 1]
        print('  corr(log k_%s, log k_xr) = %.2f' % (name, c))
    qs = np.array([r['k_len'] for r in ok]) / ka * np.array([r['k_dir'] for r in ok]) / ka * np.array([r['k_rot'] for r in ok]) / ka
    f = np.isfinite(qs)
    print('  三项乘积 vs xr:corr %.2f  中位差 %.4f' % (np.corrcoef(np.log(qs[f]), np.log(qx[f]))[0, 1], np.median(qs[f] / qx[f])))
    # 分四段(同尺子 segments 口径:按 t_a 排序等分)
    for name in ('xr', 'len', 'dir', 'rot', 'ark'):
        s = sorted(ok, key=lambda r: r['t_a'])
        parts = np.array_split(np.arange(len(s)), 4)
        if name == 'ark':
            seg = [np.nanmedian([s[i]['k_ark'] for i in p]) for p in parts]
        elif name == 'xr':
            seg = [np.nanmedian([s[i]['k_xr'] for i in p]) for p in parts]
            seg2 = [np.nanmedian([s[i]['k_xr'] / s[i]['k_ark'] / kg for i in p]) for p in parts]
            print('  分段 xr/ark/kg %s' % ' '.join('%.3f' % x for x in seg2))
        else:
            seg = [np.nanmedian([s[i]['k_' + name] / s[i]['k_ark'] for i in p]) for p in parts]
        print('  分段 %-4s %s' % (name, ' '.join('%.3f' % x for x in seg)))
    if a.out:
        json.dump({'scene': a.scene, 'xr': a.xr, 'k_global_xr_vs_arkit': kg, 'rows': rows}, open(a.out, 'w'), indent=1)


if __name__ == '__main__':
    main()
