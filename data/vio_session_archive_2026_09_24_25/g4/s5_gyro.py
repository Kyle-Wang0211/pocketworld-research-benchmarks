import sys, json, numpy as np
from g4lib import *

def load_imu(sub):
    d = np.genfromtxt(os.path.join(sub, 'imu.csv'), delimiter=',', names=True)
    return d['timestamp_ns'].astype(np.int64), np.c_[d['wx'], d['wy'], d['wz']]

class GyroInt:
    """陀螺仪积分(分段线性插值 ⇒ 累积积分是分段二次,可在任意时刻取值)。"""
    def __init__(self, t, w):
        self.t = (t - t[0]) * 1e-9; self.t0 = t[0]; self.w = w
        dt = np.diff(self.t)
        self.cum = np.vstack([np.zeros(3), np.cumsum(0.5*(w[1:]+w[:-1])*dt[:,None], 0)])
    def F(self, tn):
        x = (np.asarray(tn, np.int64) - self.t0) * 1e-9
        i = np.clip(np.searchsorted(self.t, x) - 1, 0, len(self.t)-2)
        h = x - self.t[i]; T = self.t[i+1]-self.t[i]
        w0, w1 = self.w[i], self.w[i+1]
        return self.cum[i] + w0*h[:,None] + 0.5*(w1-w0)*(h**2/T)[:,None]

def increments(P):
    ts = np.array(sorted(P), np.int64); keep = []
    th = []
    for i in range(len(ts)-1):
        if ts[i+1]-ts[i] > 50_000_000: continue
        th.append(rot_log(P[ts[i]][0].T @ P[ts[i+1]][0])); keep.append(i)
    keep = np.array(keep)
    return ts[keep], ts[keep+1], np.array(th)

def kabsch(src, dst):
    U,S,Vt = np.linalg.svd(src.T@dst); D = np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))])
    return Vt.T@D@U.T                      # dst ≈ X src

def fit(t0, t1, th, G, grid):
    """th_i ≈ g·X·(∫_{t0+s}^{t1+s} gyro − b·dt)。s>0 ⇒ 轨迹键 t 的位姿对应 IMU 时钟 t+s(轨迹超前 IMU 为负…见正文)。"""
    costs = []
    for s in grid:
        a = G.F(t0 + int(s*1e6)); b_ = G.F(t1 + int(s*1e6)); Gi = b_ - a; dt = (t1-t0)*1e-9
        bias = np.zeros(3)
        for _ in range(3):
            src = Gi - bias*dt[:,None]
            X = kabsch(src, th)
            r = (X.T @ th.T).T                      # 轨迹增量转到 IMU 系
            g = np.sum(r*src)/np.sum(src*src)
            bias = np.linalg.lstsq(-dt[:,None]*np.eye(3)[None].repeat(1,0).reshape(1,3,3).squeeze(0) if False else None, None)[0] if False else \
                   np.sum((Gi - r/g)*dt[:,None], 0)/np.sum(dt**2)
        src = Gi - bias*dt[:,None]
        X = kabsch(src, th); r = (X.T @ th.T).T; g = np.sum(r*src)/np.sum(src*src)
        c = np.mean(np.sum((r - g*src)**2, 1))
        costs.append((c, g, np.degrees(np.linalg.norm(rot_log(X)))))
    costs = np.array(costs); i = np.argmin(costs[:,0])
    if 0 < i < len(grid)-1:
        y0,y1,y2 = costs[i-1,0],costs[i,0],costs[i+1,0]; den = y0-2*y1+y2
        sb = grid[i] + (0.5*(y0-y2)/den if den else 0)*(grid[1]-grid[0])
    else: sb = grid[i]
    return sb, costs[i,1], costs[i,2], costs

grid = np.arange(-40, 40.01, 0.5)
out = {}
for key in RUNS:
    run = Run(key)
    ti, wi = load_imu(run.cfg['sub']); G = GyroInt(ti, wi)
    A = all_arkit(run); Xr = all_xr(run)
    # 合成核对:用陀螺仪积分造一条「相机」旋转轨迹,键 t 的姿态 = IMU 时钟 t+5 ms 的积分姿态
    tsA = np.array(sorted(A), np.int64)
    Rsyn = {}
    tt = np.arange(ti[0]+50_000_000, ti[-1]-50_000_000, 1_000_000, dtype=np.int64)   # 1 ms 步长积分成姿态
    Fv = G.F(tt); R = np.eye(3); Rs = [R]
    for k in range(1, len(tt)):
        R = R @ rot_exp(Fv[k]-Fv[k-1]); Rs.append(R)
    for t in tsA:
        q = t + 5_000_000
        k = int((q - tt[0])//1_000_000)
        if 0 <= k < len(tt)-1:
            Rsyn[t] = (Rs[k] @ rot_exp((Fv[k+1]-Fv[k])*((q-tt[k])/1e6)), np.zeros(3))
    a0, a1, ath = increments(Rsyn)
    s_syn, g_syn, x_syn, _ = fit(a0, a1, ath, G, grid)
    res = {'synthetic_+5ms': s_syn}
    line = f'== {key}: 合成(键 t = IMU t+5ms)⇒ s = {s_syn:+.2f} ms(应 +5.00),g={g_syn:.4f}'
    print(line)
    for nm, P in (('arkit', A), ('xr', Xr)):
        t0, t1, th = increments(P)
        sb, g, xang, costs = fit(t0, t1, th, G, grid)
        # 分 6 窗
        edges = np.linspace(t0[0], t0[-1], 7); sw = []
        for w in range(6):
            m = (t0 >= edges[w]) & (t0 < edges[w+1])
            sw.append(fit(t0[m], t1[m], th[m], G, np.arange(-30, 30.01, 0.5))[0])
        sw = np.array(sw)
        # 1 s 块 bootstrap
        rng = np.random.default_rng(3); blk = ((t0-t0[0])//1_000_000_000).astype(int); nb = blk.max()+1; bs = []
        for _ in range(100):
            idx = np.concatenate([np.where(blk==b)[0] for b in rng.integers(0, nb, nb)])
            bs.append(fit(t0[idx], t1[idx], th[idx], G, np.arange(-30, 30.01, 0.5))[0])
        bs = np.array(bs)
        # 多尺度幅值比(在最优 s 处):单帧增量 |θ_traj| / |∫gyro - b|
        print(f'   {nm:5s}: 相对 IMU 时钟 s = {sb:+.2f} ms  [块 bootstrap 95% {np.percentile(bs,2.5):+.2f}, {np.percentile(bs,97.5):+.2f}];'
              f' 6 窗 {np.round(sw,1)};幅值 g = {g:.4f};IMU→相机 旋转 {xang:.2f}°')
        res[nm] = dict(s=sb, g=g, X_deg=xang, win=sw.tolist(), boot95=[float(np.percentile(bs,2.5)), float(np.percentile(bs,97.5))])
    out[key] = res
json.dump(out, open('time_shift_gyro.json','w'), indent=1)
