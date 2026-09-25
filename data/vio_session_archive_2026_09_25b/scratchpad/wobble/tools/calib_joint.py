import sys, json, numpy as np
sys.path.insert(0, '.')
import wob, calib
from rotcal import logm, expm, R_BC
Rs, ps, taus = [], [], []
for sc in ['13f5', '6d18', '7353']:
    rc = calib.rot_calib(sc, taus=np.arange(0.0, 0.0101, 0.0005))
    Rs.append(rc['R_bc']); taus.append(rc['tau_ms'])
    print(sc, 'tau %.1f ms  misalign %.2f° axis %s rms %.3f°' % (rc['tau_ms'], rc['misalign_deg'], np.round(rc['misalign_axis']/np.linalg.norm(rc['misalign_axis']),2), rc['rms_deg']))
# 平均旋转(在占位附近的切空间平均)
d = np.mean([logm(R @ R_BC.T) for R in Rs], 0)
Rm = expm(d) @ R_BC
print('平均失准 %.2f°  轴 %s  三场与平均的偏差 %s°' % (np.degrees(np.linalg.norm(d)), np.round(d/np.linalg.norm(d),2), [round(float(np.degrees(np.linalg.norm(logm(R @ Rm.T)))),2) for R in Rs]))
for sc, tau in zip(['13f5','6d18','7353'], taus):
    for fc in (3.0, 5.0):
        lv = calib.lever_calib(sc, Rm, tau*1e-3, fc=fc)
        v = lv['all']; ps.append(v['p_bc'])
        print(sc, 'fc %.0f Hz p_bc %s mm  残差 %.4f vs 占位 %.4f' % (fc, np.round(1e3*v['p_bc'],1), v['rms'], v['rms_placeholder']))
pm = np.mean(ps, 0); print('p_bc 平均 %s mm  标准差 %s mm' % (np.round(1e3*pm,1), np.round(1e3*np.std(ps,0),1)))
# 转成 yaml 四元数 (x,y,z,w)
def r2q(R):
    w = np.sqrt(max(0, 1 + np.trace(R))) / 2
    x = (R[2,1]-R[1,2])/(4*w); y = (R[0,2]-R[2,0])/(4*w); z = (R[1,0]-R[0,1])/(4*w)
    return np.array([x,y,z,w])
# R_BC 是 180° 旋转,w≈0,改用通用算法
from numpy.linalg import eigh
def r2q_gen(R):
    K = np.array([[R[0,0]-R[1,1]-R[2,2], R[1,0]+R[0,1], R[2,0]+R[0,2], R[2,1]-R[1,2]],
                  [R[1,0]+R[0,1], R[1,1]-R[0,0]-R[2,2], R[2,1]+R[1,2], R[0,2]-R[2,0]],
                  [R[2,0]+R[0,2], R[2,1]+R[1,2], R[2,2]-R[0,0]-R[1,1], R[1,0]-R[0,1]],
                  [R[2,1]-R[1,2], R[0,2]-R[2,0], R[1,0]-R[0,1], R[0,0]+R[1,1]+R[2,2]]]) / 3
    w, V = eigh(K); q = V[:, np.argmax(w)]
    if q[0] < 0: q = -q
    return q
q = r2q_gen(Rm); print('q_bc(x,y,z,w) =', np.round(q, 7), ' 占位 [-0.7071068, 0.7071068, 0, 0](符号等价)')
print('核对 R(q) 与 Rm 差 %.4f°' % np.degrees(np.linalg.norm(logm(wob.qmat(q[None])[0] @ Rm.T))))
json.dump({'q_bc': q.tolist(), 'p_bc': pm.tolist(), 'tau_ms': taus}, open('../stats/extrinsic_from_arkit.json','w'), indent=1)
