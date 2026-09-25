#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 ARKit 轨迹反算 XRSLAM 模型(占位外参、原始加计、g=9.81)下"需要的"加计零偏 ba_need(t),与 XR 估计的 ba 对照。"""
import sys
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob
from calib import lowpass, skew, P_BC0
from rotcal import R_BC
from bastat import load_log
D = np.diag([1.0, -1.0, -1.0])

def ba_need(sc, Rbc=R_BC, pbc=P_BC0, fc=1.0, acc_scale=1.0):
    imu = wob.load_imu(sc); ark = wob.load_arkit(sc)
    ta = ark['tns'] * 1e-9; Rwc = wob.qmat(ark['Q']) @ D; C = ark['P']
    t = np.arange(ta[5], ta[-5], 0.005)
    Ci = np.stack([np.interp(t, ta, C[:, k]) for k in range(3)], 1)
    Cs = lowpass(Ci, t, 4.0); Cdd = np.gradient(np.gradient(Cs, t, axis=0), t, axis=0)
    k = np.clip(np.searchsorted(ta, t), 1, len(ta) - 1)
    k = np.where(np.abs(ta[k - 1] - t) < np.abs(ta[k] - t), k - 1, k)
    Rwb = Rwc[k] @ Rbc.T
    w = np.stack([np.interp(t, imu['t'], imu['w'][:, c]) for c in range(3)], 1)
    am = np.stack([np.interp(t, imu['t'], imu['a'][:, c]) for c in range(3)], 1)
    ws = lowpass(w, t, 4.0); ams = lowpass(am, t, 4.0) * acc_scale; wd = np.gradient(ws, t, axis=0)
    g_up = np.array([0, 9.81, 0])
    lev = np.array([(skew(wd[n]) + skew(ws[n]) @ skew(ws[n])) @ pbc for n in range(len(t))])
    f_pred = np.einsum('nji,nj->ni', Rwb, Cdd + g_up) - lev   # 体系下的比力(不含零偏)
    bn = ams - f_pred
    return t, lowpass(bn, t, fc)

if __name__ == '__main__':
    for sc, tag in [('13f5', '13f5_log_r1'), ('6d18', '6d18_log_r1'), ('7353', '7353_log_r1'), ('fb5d', 'fb5d_log_r1')]:
        t, bn = ba_need(sc)
        ev = load_log(tag); L = ev['latest']
        tl = np.array([d['t'] for d in L]); ba = np.array([d['ba'] for d in L])
        bni = np.stack([np.interp(tl, t, bn[:, c]) for c in range(3)], 1)
        m = (tl > t[0] + 2) & (tl < t[-1] - 2)
        print('== %s  ba_need(ARKit 反算,1 Hz 低通) 范围 %s  | XR ba 范围 %s' % (sc, np.round(np.ptp(bni[m], 0), 3), np.round(np.ptp(ba[m], 0), 3)))
        for c in range(3):
            print('   轴%d  corr(XR ba, ba_need) %+.2f   均值 XR %+.3f need %+.3f' % (c, np.corrcoef(ba[m, c], bni[m, c])[0, 1], ba[m, c].mean(), bni[m, c].mean()))
        # 不同模型下 ba_need 的变化幅度(越小越说明该模型更自洽)
        for name, kw in [('占位外参', {}), ('ARKit 旋转外参', 'qark'), ('加计×1/0.993', {'acc_scale': 1 / 0.993})]:
            if kw == 'qark':
                import json
                ex = json.load(open(wob.W + '/stats/extrinsic_from_arkit.json'))
                kw = {'Rbc': wob.qmat(np.array([ex['q_bc']]))[0]}
            t2, b2 = ba_need(sc, **kw)
            mm = (t2 > t2[0] + 2) & (t2 < t2[-1] - 2)
            print('   模型 %-14s ba_need 标准差 %s m/s²' % (name, np.round(b2[mm].std(0), 4)))
