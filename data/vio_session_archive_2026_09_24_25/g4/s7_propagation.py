import sys, csv, json, numpy as np
from g4lib import *
from gyrolib import load_imu, GyroInt, kabsch

for key in RUNS:
    run = Run(key)
    ti, wi = load_imu(run.cfg['sub']); G = GyroInt(ti, wi)
    rows = list(csv.DictReader(open(run.xr_csv)))
    t = np.array([int(r['t_ns']) for r in rows], np.int64)
    te = np.array([round(float(r['engine_t'])*1e9) for r in rows], np.int64)     # 引擎自己的时间
    R = [LR.quat_to_rmat(*[float(r[k]) for k in ('qx','qy','qz','qw')]) for r in rows]
    fr = np.array([int(r['recording_frame']) for r in rows])
    ft = {int(r['recording_frame']): r for r in csv.DictReader(open(os.path.join(run.cfg['rep'], 'frame_timing.csv')))}
    ok = np.where((np.diff(t) < 50_000_000))[0]
    th = np.array([rot_log(R[i].T @ R[i+1]) for i in ok])
    A = all_arkit(run)
    # IMU→相机 旋转:用 ARKit(与陀螺在 s=0 精确对齐)求一次,之后对 XR 共用
    ta = np.array(sorted(A), np.int64); ka = np.where(np.diff(ta) < 50_000_000)[0]
    tha = np.array([rot_log(A[ta[i]][0].T @ A[ta[i+1]][0]) for i in ka])
    Ga = G.F(ta[ka+1]) - G.F(ta[ka]); X = kabsch(Ga, tha)
    ba = np.sum(Ga - (X.T @ tha.T).T, 0) / np.sum((ta[ka+1]-ta[ka])*1e-9)     # 粗 bias(ARKit 口径)
    res = {}
    for nm, s in (('s=+engine_t(喂的时刻)', None), ('s=0', 0), ('s=-6ms', -6)):
        if s is None:
            Gi = G.F(te[ok+1]) - G.F(te[ok])
        else:
            Gi = G.F(t[ok+1] + s*1_000_000) - G.F(t[ok] + s*1_000_000)
        dt = (t[ok+1]-t[ok])*1e-9
        # 用 XR 自己的数据估 bias(XR 的 bg 可能与 ARKit 不同):最小二乘
        r_imu = (X.T @ th.T).T
        b = np.sum(Gi - r_imu, 0)/np.sum(dt)
        e = np.degrees(np.linalg.norm(r_imu - (Gi - np.outer(dt, b)), axis=1))
        res[nm] = e
        print(f'{key} XR 帧间增量 vs 陀螺积分[{nm}]:残差 中位 {np.median(e):.4f}°  <0.01°: {np.mean(e<0.01)*100:.0f}%  <0.03°: {np.mean(e<0.03)*100:.0f}%  p90 {np.percentile(e,90):.3f}°')
    # 残差大(后端校正)的帧 与 frame_timing 的 sw_solves / bk_track_n 的关系
    e = res['s=+engine_t(喂的时刻)']
    sws = np.array([float(ft.get(int(fr[i+1]), {}).get('sw_solves', 'nan')) for i in ok])
    print(f'   sw_solves 分布(下一帧):', dict(zip(*np.unique(sws, return_counts=True))))
    for v in np.unique(sws):
        m = sws == v
        if m.sum() > 5: print(f'   sw_solves={v:g}: n={m.sum()} 残差中位 {np.median(e[m]):.4f}°')
