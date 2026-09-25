#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后端 kf_final(10 Hz,body 位姿 + 速度)插值到任意录制帧(诊断用):
旋转:R(t)=R_k·Exp(∫ω)·Exp(α·log(残差)) —— 陀螺积分后把端点残差按时间比例分摊;位置:三次 Hermite(端点速度)。
输出相机位姿(用该次回放 yaml 的 q_bc/p_bc),键为录制帧 t_ns。"""
import json, sys
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob
from rotcal import logm, expm
from gyrofit import GyroInt
from backend_eval import yaml_ext

def kf_states(tag, ev='kf_final'):
    mp = {}
    for ln in open(wob.W + '/runs/%s.map' % tag):
        a, b = ln.split(); mp[a] = int(b)
    S = {}
    for ln in open(wob.W + '/runs/%s.jsonl' % tag):
        try: d = json.loads(ln)
        except Exception: continue
        if d['ev'] != ev: continue
        k = '%.9f' % d['t']
        if k in mp and k not in S:
            S[k] = (d['t'], mp[k], wob.qmat(np.array([d['q']]))[0], np.array(d['p']), np.array(d['v']), np.array(d.get('bg', [0, 0, 0])))
    return sorted(S.values(), key=lambda x: x[0]), mp

def interp_to(sc, tag, want_tns, ev='kf_final'):
    st, mp = kf_states(tag, ev)
    Rbc, pbc = yaml_ext(tag)
    te = np.array([s[0] for s in st])
    eng_of = {v: float(k) for k, v in mp.items()}  # t_ns -> 引擎时间
    G = GyroInt(sc)
    out = {}
    for tn in want_tns:
        if tn not in eng_of: continue
        t = eng_of[tn]
        i = np.searchsorted(te, t) - 1
        if i < 0 or i + 1 >= len(te) or te[i + 1] - te[i] > 0.25: continue
        t0, _, R0, p0, v0, bg0 = st[i]; t1, _, R1, p1, v1, _ = st[i + 1]
        h = t1 - t0; a = (t - t0) / h
        dR01 = expm(G.F(np.array([t1]))[0] - G.F(np.array([t0]))[0] - bg0 * h)
        res = logm(dR01.T @ (R0.T @ R1))
        R = R0 @ expm(G.F(np.array([t]))[0] - G.F(np.array([t0]))[0] - bg0 * (t - t0)) @ expm(a * res)
        h00 = 2 * a**3 - 3 * a**2 + 1; h10 = a**3 - 2 * a**2 + a; h01 = -2 * a**3 + 3 * a**2; h11 = a**3 - a**2
        p = h00 * p0 + h10 * h * v0 + h01 * p1 + h11 * h * v1
        out[tn] = (R @ Rbc, p + R @ pbc)
    return out
