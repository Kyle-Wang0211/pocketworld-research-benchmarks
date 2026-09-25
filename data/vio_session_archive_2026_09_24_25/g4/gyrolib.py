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

