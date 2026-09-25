import sys, json, pickle, numpy as np
from g4lib import *

def omega_series(P):
    ts = np.array(sorted(P), dtype=np.int64)
    tm, w = [], []
    for i in range(len(ts)-1):
        dt = (ts[i+1]-ts[i])*1e-9
        if dt > 0.05: continue
        w.append(rot_log(P[ts[i]][0].T @ P[ts[i+1]][0])/dt)    # 相机系角速度
        tm.append(0.5*(ts[i]+ts[i+1]))
    return np.array(tm), np.array(w)

def fit_shift(ta, wa, tx, wx, X, sel=None, grid=np.arange(-40, 40.01, 0.25)):
    """找 s(ms)使 ω_ark(t) ≈ X·ω_xr(t + s)。s>0 ⇒ XR 在 t+s 的位姿才对应 t 时刻(XR 位姿滞后 s)。"""
    wxr = (X @ wx.T).T
    best, cost = None, []
    m = np.ones(len(ta), bool) if sel is None else sel
    for s in grid:
        q = ta[m] + s*1e6
        ok = (q > tx[0]) & (q < tx[-1])
        wi = np.stack([np.interp(q[ok], tx, wxr[:,k]) for k in range(3)], 1)
        # 允许一个幅值比 g(最小二乘)
        a = wa[m][ok]
        g = np.sum(a*wi)/np.sum(wi*wi)
        c = np.mean(np.sum((a - g*wi)**2, 1))
        cost.append((c, g))
    cost = np.array(cost)
    i = np.argmin(cost[:,0])
    # 抛物线细化
    if 0 < i < len(grid)-1:
        y0,y1,y2 = cost[i-1,0],cost[i,0],cost[i+1,0]
        d = 0.5*(y0-y2)/(y0-2*y1+y2) if (y0-2*y1+y2)!=0 else 0
        sbest = grid[i] + d*(grid[1]-grid[0])
    else:
        sbest = grid[i]
    return sbest, cost[i,1], cost[:,0]

def handeye_X(A, Xr):
    ts = sorted(set(A)&set(Xr)); va, vx = [], []
    for i in range(len(ts)-3):
        t0,t1 = ts[i], ts[i+3]
        if t1-t0 > 150_000_000: continue
        wa = rot_log(A[t0][0].T@A[t1][0]); wx = rot_log(Xr[t0][0].T@Xr[t1][0])
        if np.linalg.norm(wa) > np.radians(1.0): va.append(wa); vx.append(wx)
    va, vx = np.array(va), np.array(vx)
    U,S,Vt = np.linalg.svd(vx.T@va); D = np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))])
    return Vt.T@D@U.T

