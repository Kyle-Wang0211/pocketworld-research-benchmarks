#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""后端轨迹(latest / kf_final,10 Hz)vs 同帧 API 输出:全局 k、ATE、2 s/4 s 窗尺度离散、四段。
后端 p/q 是 body 位姿 ⇒ 相机中心 C = p + R_wb p_bc,R_wc = R_wb R_bc(p_bc/q_bc 取该次回放 yaml)。"""
import re, sys
import numpy as np
sys.path.insert(0, '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/tools')
import wob
from gyrofit import backend_traj

def yaml_ext(tag):
    cmd = open(wob.W + '/runs/%s.cmd' % tag).read()
    dev = re.search(r'dev=(\S+)', cmd).group(1)
    txt = open(wob.W + '/cfg/' + dev).read()
    q = [float(x) for x in re.search(r'q_bc:\s*\[([^\]]+)\]', txt).group(1).split(',')]
    p = np.array([float(x) for x in re.search(r'p_bc:\s*\[([^\]]+)\]', txt).group(1).split(',')])
    return wob.qmat(np.array([q]))[0], p

def to_xr(tns, R, P, Rbc, pbc):
    C = P + np.einsum('nij,j->ni', R, pbc)
    Rc = R @ Rbc
    # 旋转矩阵 → 四元数(x,y,z,w)
    from calib_joint_q import r2q
    return dict(tns=tns, P=C, Q=np.array([r2q(r) for r in Rc]))

def metrics(sc, xr, min_n):
    ark = wob.load_arkit(sc); J = wob.join(xr, ark)
    kg = wob.k_sim3(J['X'], J['Y']); ate = 100 * wob.ate_sim3(J['X'], J['Y'])
    e2 = np.array([w['k_sim3'] / kg - 1 for w in wob.windows(J, 2.0, 2.0, min_n=min_n)])
    e4 = np.array([w['k_sim3'] / kg - 1 for w in wob.windows(J, 4.0, 0.5, min_n=2 * min_n)])
    q = wob.quarters(J)
    return 'n %4d k %.4f ATE %5.2f | Q %s | 2s|e| med %4.1f%% max %4.1f%% sd %4.1f%% | 4s sd %4.1f%% [%+.1f,%+.1f]' % (
        len(J['t']), kg, ate, ' '.join('%.3f' % x for x in q), 100 * np.median(np.abs(e2)), 100 * np.max(np.abs(e2)),
        100 * np.std(e2), 100 * np.std(e4), 100 * e4.min(), 100 * e4.max())

if __name__ == '__main__':
    for a in sys.argv[1:]:
        sc, tag = a.split(':')
        Rbc, pbc = yaml_ext(tag)
        api = wob.load_xr_mac(tag)
        tl, Rl, Pl = backend_traj(tag, 'latest'); tk, Rk, Pk = backend_traj(tag, 'kf_final')
        sel = np.isin(api['tns'], tl)
        api10 = dict(tns=api['tns'][sel], P=api['P'][sel], Q=api['Q'][sel])
        print('%-5s %-16s api(30Hz)      %s' % (sc, tag, metrics(sc, api, 30)))
        print('%-5s %-16s api@后端帧     %s' % (sc, tag, metrics(sc, api10, 10)))
        print('%-5s %-16s 后端 latest    %s' % (sc, tag, metrics(sc, to_xr(tl, Rl, Pl, Rbc, pbc), 10)))
        print('%-5s %-16s 后端 kf_final  %s' % (sc, tag, metrics(sc, to_xr(tk, Rk, Pk, Rbc, pbc), 10)))
