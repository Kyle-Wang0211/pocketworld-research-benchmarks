import json, numpy as np
from g4lib import *
from gyrolib import load_imu, GyroInt, increments, kabsch
sh = json.load(open('time_shift_gyro.json'))
for key in RUNS:
    run = Run(key); ti, wi = load_imu(run.cfg['sub']); G = GyroInt(ti, wi)
    Xs = {}
    for nm, P in (('arkit', all_arkit(run)), ('xr', all_xr(run))):
        t0, t1, th = increments(P); s = sh[key][nm]['s']
        Gi = G.F(t1 + int(s*1e6)) - G.F(t0 + int(s*1e6))
        m = np.linalg.norm(Gi, axis=1) > np.radians(1.0)
        Xs[nm] = kabsch(Gi[m], th[m])
    d = np.degrees(np.linalg.norm(rot_log(Xs['arkit'].T @ Xs['xr'])))
    v = np.degrees(rot_log(Xs["arkit"].T @ Xs["xr"])); print(f"{key}: 相机轴差 {d:.3f}°,旋转向量(相机系,度)= {np.round(v,3)}")
