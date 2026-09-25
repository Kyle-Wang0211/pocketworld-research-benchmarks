import sys, json, pickle, numpy as np
from g4lib import *

def Kmat(k): return np.array([[k[0],0,k[2]],[0,k[1],k[3]],[0,0,1.0]])
def skew(t): return np.array([[0,-t[2],t[1]],[t[2],0,-t[0]],[-t[1],t[0],0]])

def epi_stats(run):
    """每对:图像 RANSAC 本质矩阵 → R_img, t_img;各轨迹相对位姿与之的旋转差/平移方向差;E 内点在各轨迹 E 下的 Sampson 误差(像素)。"""
    rows = []
    for fa, fb, pa, pb in run.matched:
        if len(pa) < 15: rows.append(None); continue
        Ka, Kb = Kmat(fa['K']), Kmat(fb['K'])
        na = cv2.undistortPoints(pa.reshape(-1,1,2), Ka, None).reshape(-1,2)
        nb = cv2.undistortPoints(pb.reshape(-1,1,2), Kb, None).reshape(-1,2)
        f = 0.5*(fa['K'][0]+fb['K'][0])
        E, mask = cv2.findEssentialMat(na, nb, np.eye(3), method=cv2.RANSAC, prob=0.9999, threshold=1.0/f)
        if E is None or E.shape != (3,3): rows.append(None); continue
        _, Ri, ti, m2 = cv2.recoverPose(E, na, nb, np.eye(3), mask=mask.copy())
        inl = mask.ravel().astype(bool)
        r = {'n_match': len(pa), 'n_inl': int(inl.sum())}
        for name, poses in (('arkit', run.ark), ('xr', run.xr)):
            Rr, tr = LR.rel_pose(poses[fa['t_ns']], poses[fb['t_ns']])
            r[name+'_rot_err_deg'] = np.degrees(np.linalg.norm(rot_log(Ri.T @ Rr)))
            tn = tr/np.linalg.norm(tr)
            r[name+'_tdir_err_deg'] = np.degrees(np.arccos(np.clip(abs(float(tn @ ti.ravel())),-1,1)))
            Et = skew(tr) @ Rr
            x1 = np.c_[na[inl], np.ones(inl.sum())]; x2 = np.c_[nb[inl], np.ones(inl.sum())]
            Ex1 = (Et @ x1.T).T; Etx2 = (Et.T @ x2.T).T
            num = np.sum(x2*Ex1,1)**2
            den = Ex1[:,0]**2+Ex1[:,1]**2+Etx2[:,0]**2+Etx2[:,1]**2
            r[name+'_sampson_px_med'] = float(np.median(np.sqrt(num/den))*f)
        # XR vs ARKit 相对旋转差(与图像无关)
        Ra,_ = LR.rel_pose(run.ark[fa['t_ns']], run.ark[fb['t_ns']])
        Rx,_ = LR.rel_pose(run.xr[fa['t_ns']], run.xr[fb['t_ns']])
        r['xr_vs_ark_rot_deg'] = np.degrees(np.linalg.norm(rot_log(Ra.T @ Rx)))
        r['rel_rot_mag_deg'] = np.degrees(np.linalg.norm(rot_log(Ra)))
        rows.append(r)
    return rows

def handeye(run):
    """两条轨迹整段相对旋转 ΔR 之间是否存在一个常量相机系偏差 X:ΔR_xr ≈ X^T ΔR_ark X。
    用旋转轴对齐(Kabsch on rotation vectors)。X≈I ⇒ 同一相机轴约定。"""
    A = all_arkit(run); Xr = all_xr(run)
    ts = sorted(set(A)&set(Xr))
    va, vx = [], []
    for i in range(len(ts)-3):
        t0, t1 = ts[i], ts[i+3]
        if t1 - t0 > 150_000_000: continue
        wa = rot_log(A[t0][0].T @ A[t1][0]); wx = rot_log(Xr[t0][0].T @ Xr[t1][0])
        if np.linalg.norm(wa) > np.radians(1.0):
            va.append(wa); vx.append(wx)
    va, vx = np.array(va), np.array(vx)
    H = vx.T @ va
    U,S,Vt = np.linalg.svd(H)
    D = np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))])
    X = Vt.T @ D @ U.T          # va ≈ X vx
    ang = np.degrees(np.linalg.norm(rot_log(X)))
    # 相机系下角速度幅值比(陀螺尺度)
    ratio = np.median(np.linalg.norm(vx,axis=1)/np.linalg.norm(va,axis=1))
    return ang, ratio, len(va)

for key in RUNS:
    run = Run(key)
    rows = epi_stats(run)
    cur = pickle.load(open(f'curve_{key}.pkl','rb'))
    ok_a = np.isfinite(ratios_of(cur['arkit']['curve_pairs'][0])); ok_x = np.isfinite(ratios_of(cur['xr']['curve_pairs'][0]))
    R = [r for r in rows if r]
    def med(k, sel=None):
        v = [r[k] for r,s in zip(rows, sel if sel is not None else [True]*len(rows)) if r and s]
        return np.median(v), np.percentile(v,90)
    print(f'== {key}  帧对 {len(rows)},有 E 的 {len(R)}')
    for k in ('arkit_rot_err_deg','xr_rot_err_deg','arkit_tdir_err_deg','xr_tdir_err_deg','arkit_sampson_px_med','xr_sampson_px_med','xr_vs_ark_rot_deg','rel_rot_mag_deg'):
        m, p90 = med(k)
        print(f'   {k:24s} 中位 {m:7.3f}   p90 {p90:7.3f}')
    # XR 有效 vs 被砍的帧对
    m1,_ = med('xr_rot_err_deg', ok_x); m2,_ = med('xr_rot_err_deg', ~ok_x)
    print(f'   XR 旋转误差:XR 有效帧对 中位 {m1:.3f}°,XR 被砍帧对 中位 {m2:.3f}°')
    ang, ratio, n = handeye(run)
    print(f'   常量相机系偏差 X(ΔR_ark ≈ X ΔR_xr)= {ang:.3f}°,角增量幅值比 xr/ark 中位 {ratio:.4f}(n={n})')
    pickle.dump(rows, open(f'epi_{key}.pkl','wb'))
