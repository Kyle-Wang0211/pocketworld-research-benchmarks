import sys, json, numpy as np
from g4lib import *
from gyrolib import load_imu, GyroInt, increments, kabsch
for key in RUNS:
    run = Run(key)
    ti, wi = load_imu(run.cfg['sub']); G = GyroInt(ti, wi)
    for nm, P in (('arkit', all_arkit(run)), ('xr', all_xr(run))):
        t0, t1, th = increments(P)
        Gi = G.F(t1) - G.F(t0)                     # s = 0 的陀螺积分
        X = kabsch(Gi, th); r = (X.T @ th.T).T
        mg = np.linalg.norm(Gi, axis=1); big = mg > np.radians(1.5)
        # 沿陀螺积分方向的投影比(带符号)
        proj = np.sum(r*Gi, 1)/mg**2
        pr = proj[big]
        h = np.histogram(pr, bins=[-1,0.25,0.5,0.75,0.9,1.1,1.25,1.5,1.75,3])[0]
        print(f'{key} {nm:5s} 单帧增量投影比(|∫gyro|>1.5°,n={big.sum()}):中位 {np.median(pr):.3f}  分布 '
              + ' '.join(f'{a}-{b}:{c}' for a, b, c in zip([-1,0.25,0.5,0.75,0.9,1.1,1.25,1.5,1.75],[0.25,0.5,0.75,0.9,1.1,1.25,1.5,1.75,3], h)))
