#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 给 LiDAR 米尺(lidar_ruler.py --camera)写相机位姿 TUM,时间 = 录制帧 t_ns(整数纳秒)。
  front  前端 CAMERA_POSE(keyed.csv),米尺子集帧都是引擎收下的帧 ⇒ 原值,不插值;
  final  后端定稿(backend.csv kind 2 / 3,带 v / bg 的新出口):深度帧不在后端帧上(录制帧号 mod 3 错开),
         照 wobble/tools/make_tums.py 的 interp_backend 原样:旋转 = 陀螺积分 + 端点残差线性分摊,位置 = Hermite(p, v)。
引擎时间取回放 .map 里该帧的 engine_t(逐位)。只作米尺诊断,不进任何产品路径。
用法:make_ruler_tums.py <scene> <tag> <out_prefix>"""
import csv
import re
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
sys.path.insert(0, SP + '/wobble/tools')
import wob  # noqa: E402
from calib_joint_q import r2q  # noqa: E402
from gyrofit import GyroInt  # noqa: E402
from make_tums import interp_backend, fmt_t  # noqa: E402

W = SP + '/preint/runs/'


def ext(tag):
    cmd = open(W + tag + '.cmd').read()
    dev = re.search(r'dev=(\S+)', cmd).group(1)
    txt = open(SP + '/preint/cfg/' + dev).read()
    q = [float(x) for x in re.search(r'q_bc:\s*\[([^\]]+)\]', txt).group(1).split(',')]
    p = np.array([float(x) for x in re.search(r'p_bc:\s*\[([^\]]+)\]', txt).group(1).split(',')])
    return wob.qmat(np.array([q]))[0], p


def main(sc, tag, out):
    Rbc, pbc = ext(tag)
    G = GyroInt(sc)
    eng = {}
    for ln in open(W + tag + '.map'):
        a, b = ln.split()
        eng[int(b)] = float(a)
    sub = np.loadtxt(wob.rdir(sc) + '/ruler_subset/camera_index.csv', delimiter=',', skiprows=1, dtype=np.int64)[:, 0]
    st, win = {}, {}
    for r in csv.DictReader(open(W + tag + '.backend.csv')):
        if int(r['t_ns']) < 0 or r['kind'] not in ('2', '3'):
            continue
        t = float(r['engine_t'])
        R = wob.qmat(np.array([[float(r['body_q' + c]) for c in 'xyzw']]))[0]
        p = np.array([float(r['body_t' + c]) for c in 'xyz'])
        v = np.array([float(r['v' + c]) for c in 'xyz'])
        bg = np.array([float(r['bg' + c]) for c in 'xyz'])
        (st if r['kind'] == '2' else win)[t] = (t, R, p, v, bg)
    for t, x in win.items():
        st.setdefault(t, x)   # 定稿 = Final;收尾仍在窗口的帧取整窗快照(同 eval3)
    states = sorted(st.values(), key=lambda x: x[0])
    rows_f, rows_b = [], []
    front = {int(r['t_ns']): r for r in csv.DictReader(open(W + tag + '.keyed.csv'))}
    for tn in sub.tolist():
        if tn in front:
            r = front[tn]
            rows_f.append('%s %s %s %s %s %s %s %s' % (fmt_t(tn), r['tx'], r['ty'], r['tz'], r['qx'], r['qy'], r['qz'], r['qw']))
        if tn in eng:
            x = interp_backend(G, states, eng[tn], Rbc, pbc)
            if x is not None:
                R, p = x
                rows_b.append('%s %.7f %.7f %.7f %.7f %.7f %.7f %.7f' % (fmt_t(tn), *p, *r2q(R)))
    open(out + '_front.tum', 'w').write('\n'.join(rows_f) + '\n')
    open(out + '_final.tum', 'w').write('\n'.join(rows_b) + '\n')
    print(sc, tag, '子集帧 %d:前端 %d 行,后端定稿插值 %d 行' % (len(sub), len(rows_f), len(rows_b)))


if __name__ == '__main__':
    main(*sys.argv[1:4])
