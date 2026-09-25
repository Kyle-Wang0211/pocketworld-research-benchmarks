#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[preint 2026-09-25] 诊断:陀螺样本的时间语义。把陀螺按三种规则积成角度累积 F(t):
  trap  样本间线性(= gyrofit.GyroInt,段内梯形)
  left  左端保持(样本 k 管 [t_k, t_k+1))
  right 右端保持(样本 k 管 (t_k−1, t_k],即「样本 = 前一区间的平均角速度」)
时间偏移 s 自由拟合(纯平移被吸收),比较残差:谁与视觉(ARKit / 引擎后端)的旋转增量更一致。
用法:gyro_rule.py <scene> [tag ...](不给 tag 只算 ARKit 全帧 33 ms)"""
import sys

import numpy as np

SP = '/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0, SP + '/preint/tools')
sys.path.insert(0, SP + '/wobble/tools')
import gyrofit  # noqa: E402
import preint_eval as PE  # noqa: E402
import wob  # noqa: E402
from rotcal import logm  # noqa: E402

GRID = np.arange(-0.03, 0.0301, 0.00025)


class Hold:
    def __init__(self, sc, side):
        imu = wob.load_imu(sc)
        self.t = imu['t']; self.w = imu['w']; self.side = side
        dt = np.diff(self.t)
        wv = self.w[:-1] if side == 'left' else self.w[1:]
        self.wv = wv
        self.cum = np.vstack([np.zeros(3), np.cumsum(wv * dt[:, None], 0)])

    def F(self, x):
        i = np.clip(np.searchsorted(self.t, x) - 1, 0, len(self.t) - 2)
        h = x - self.t[i]
        return self.cum[i] + self.wv[i] * h[:, None]


def incr(t, R, gap):
    keep = np.nonzero(np.diff(t) < gap)[0]
    return t[keep], t[keep + 1], np.array([logm(R[i].T @ R[i + 1]) for i in keep])


def main(sc, tags):
    Gs = {'trap': gyrofit.GyroInt(sc), 'left': Hold(sc, 'left'), 'right': Hold(sc, 'right')}
    A = wob.load_arkit(sc); RA = wob.qmat(A['Q']) @ PE.D
    sets = [('ARKit 全帧 33 ms', incr(A['tns'] * 1e-9, RA, 0.2))]
    for tag in tags:
        _, fin = PE.load_backend_full(PE.W + tag + '.backend.csv')
        ks = sorted(fin)
        sets.append(('%s 后端定稿' % tag, incr(np.array([fin[k][2] for k in ks]), np.array([fin[k][0] for k in ks]), 0.4)))
        ia = {int(x): i for i, x in enumerate(A['tns'])}
        kk = [k for k in ks if k in ia]
        sets.append(('ARKit@%s 后端帧' % tag.split('_')[0], incr(np.array(kk) * 1e-9, np.array([RA[ia[k]] for k in kk]), 0.4)))
    for name, (t0, t1, th) in sets:
        r = {k: gyrofit.fit(G, t0, t1, th, GRID) for k, G in Gs.items()}
        print('%-5s %-34s ' % (sc, name) + ' | '.join('%s: s %+6.2f ms 残差 %.4f° g %.4f' % (k, v['s_ms'], v['jitter_deg'], v['g']) for k, v in r.items()))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
