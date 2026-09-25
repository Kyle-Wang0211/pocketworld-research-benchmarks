import sys, json, pickle, numpy as np
from g4lib import *
from timelib import omega_series, fit_shift, handeye_X

def Kmat(k): return np.array([[k[0],0,k[2]],[0,k[1],k[3]],[0,0,1.0]])
def skew(t): return np.array([[0,-t[2],t[1]],[t[2],0,-t[0]],[-t[1],t[0],0]])

# ① 符号核对:XR' 键 t 的位姿 = ARKit 在 t+5ms 的位姿(XR' 超前 5 ms)⇒ fit_shift 应给 s = -5
run = Run('13f5'); A = all_arkit(run); IA = Interp(A)
syn = {}
for t in sorted(A):
    p = IA(t + 5_000_000)
    if p: syn[t] = p
ta, wa = omega_series(A); ts_, ws = omega_series(syn)
print('符号核对:XR\'(t)=ARKit(t+5ms) ⇒ s =', round(fit_shift(ta, wa, ts_, ws, np.eye(3))[0], 2), 'ms(应为 -5)')

# ② 多尺度角增量幅值比 xr/ark(k 帧增量)
for key in RUNS:
    run = Run(key); A = all_arkit(run); Xr = all_xr(run)
    s_best = json.load(open('time_shift_omega.json'))[key]['s']
    IX = Interp(Xr)
    Xs = {t: IX(t + int(s_best*1e6)) for t in A}; Xs = {t: p for t, p in Xs.items() if p}
    line = []
    for k in (1, 3, 10, 30):
        for nm, XX in (('原始', Xr), ('平移后', Xs)):
            ts = sorted(set(A) & set(XX)); r = []
            for i in range(len(ts)-k):
                t0, t1 = ts[i], ts[i+k]
                if t1 - t0 > (k*33.4+20)*1e6: continue
                a = np.linalg.norm(rot_log(A[t0][0].T@A[t1][0])); x = np.linalg.norm(rot_log(XX[t0][0].T@XX[t1][0]))
                if a > np.radians(1.0): r.append(x/a)
            line.append(f'{k}帧 {nm} {np.median(r):.4f}')
    print(f'{key} 角增量幅值比 xr/ark 中位:', ';'.join(line))

# ③ 图像裁判:Sampson 误差 vs 位姿时间平移 s,和旋转增量缩放 (1+eps)
def sampson_eval(run, P_interp, s_ms, eps=0.0):
    per = []
    for (fa, fb, pa, pb), (na, nb, inl, f) in zip(run.matched, run._norm):
        if inl is None: continue
        pa_ = P_interp(fa['t_ns'] + int(s_ms*1e6)); pb_ = P_interp(fb['t_ns'] + int(s_ms*1e6))
        if pa_ is None or pb_ is None: continue
        Rr, tr = LR.rel_pose(pa_, pb_)
        if eps: Rr = rot_exp((1+eps)*rot_log(Rr))
        Et = skew(tr) @ Rr
        x1 = np.c_[na[inl], np.ones(inl.sum())]; x2 = np.c_[nb[inl], np.ones(inl.sum())]
        Ex1 = (Et@x1.T).T; Etx2 = (Et.T@x2.T).T
        e = np.sqrt(np.sum(x2*Ex1,1)**2/(Ex1[:,0]**2+Ex1[:,1]**2+Etx2[:,0]**2+Etx2[:,1]**2))*f
        per.append(np.median(e))
    return np.median(per), len(per)

res = {}
for key in RUNS:
    run = Run(key)
    run._norm = []
    for fa, fb, pa, pb in run.matched:
        if len(pa) < 15: run._norm.append((None,None,None,None)); continue
        Ka, Kb = Kmat(fa['K']), Kmat(fb['K'])
        na = cv2.undistortPoints(pa.reshape(-1,1,2), Ka, None).reshape(-1,2)
        nb = cv2.undistortPoints(pb.reshape(-1,1,2), Kb, None).reshape(-1,2)
        f = 0.5*(fa['K'][0]+fb['K'][0])
        E, mask = cv2.findEssentialMat(na, nb, np.eye(3), method=cv2.RANSAC, prob=0.9999, threshold=1.0/f)
        if E is None or E.shape != (3,3): run._norm.append((None,None,None,None)); continue
        run._norm.append((na, nb, mask.ravel().astype(bool), f))
    IA = Interp(all_arkit(run)); IX = Interp(all_xr(run))
    grid = np.arange(-24, 24.1, 2.0)
    r = {}
    for nm, I in (('arkit', IA), ('xr', IX)):
        c = np.array([sampson_eval(run, I, s)[0] for s in grid])
        i = np.argmin(c)
        # 细化
        fine = np.arange(grid[i]-2, grid[i]+2.01, 0.25)
        cf = np.array([sampson_eval(run, I, s)[0] for s in fine])
        sb = fine[np.argmin(cf)]
        ce = {eps: sampson_eval(run, I, sb, eps)[0] for eps in (-0.08,-0.06,-0.04,-0.02,0,0.02,0.04,0.06,0.08)}
        e_best = min(ce, key=ce.get)
        c0 = sampson_eval(run, I, 0)[0]
        r[nm] = dict(grid=grid.tolist(), cost=c.tolist(), s_best=float(sb), cost_at_0=float(c0), cost_best=float(cf.min()), eps_curve={str(k): float(v) for k, v in ce.items()}, eps_best=e_best)
        print(f'{key} {nm:5s}: 图像最优位姿时移 s = {sb:+.2f} ms(Sampson 中位 {cf.min():.3f} px;s=0 时 {c0:.3f} px);'
              f'在最优 s 处旋转缩放最优 eps = {e_best:+.2f}  曲线 ' + ' '.join(f'{k:+.2f}:{v:.3f}' for k, v in ce.items()))
    res[key] = r
json.dump(res, open('referee.json','w'), indent=1)
