# -*- coding: utf-8 -*-
"""焦距偏小的排他性检验(只读诊断)。对极 Sampson 误差(像素,截断 2 px)下拟合焦距倍率 α,逐项换假设:
 ① fx/fy 分开拟合;② 主点同时放开;③ 按对焦状态(报的 fx)分组;④ 位姿时间整体平移 δ;⑤ 卷帘快门(逐行时间 × ARKit 角速度);
 ⑥ 陀螺旋转版 + 外参扰动 0.68°;⑦ 陀螺 / ARKit 旋转角之比。"""
import sys, os, json
sys.dont_write_bytecode=True
import numpy as np
LRDIR=os.path.expanduser('~/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler')
sys.path.insert(0,LRDIR)
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0,SP+'/wobble/tools')
import lidar_ruler as LR, wob
from rotcal import logm, expm, gyro_integrate
BG={'13f5':[-0.0063,0.0001,0.0029],'6d18':[-0.0066,0.0015,0.0021],'7353':[-0.0008,-0.0051,0.0051]}
sc=sys.argv[1]
Z=np.load('pts_%s.npz'%sc); X=Z['pts']; PR=Z['pairs']
pid,ua,va,ub,vb,z,zb,ea,eb=X.T[:9]; pid=pid.astype(int)
rec='full_'+sc
ts=[int(l.split(',')[0]) for l in open(rec+'/camera_index.csv').read().split('\n')[1:] if l]
ark,_=LR.arkit_poses(rec,rec+'/arkit_poses.tum',ts)
keys=np.array(sorted(ark)); Rk=np.array([ark[k][0] for k in keys]); Ck=np.array([ark[k][1] for k in keys])
intr={}
for l in open(rec+'/intrinsics.jsonl'):
    if l.strip():
        d=json.loads(l); intr[int(round(d['t']*1e9))]=d['intrinsics_fxfycxcy']
ik=np.array(sorted(intr)); near=lambda arr,t: int(arr[np.argmin(np.abs(arr-t))])
def pose_at(t):   # t 秒;ARKit 位姿(OpenCV 轴)slerp/线性插值
    x=t*1e9; i=int(np.clip(np.searchsorted(keys,x)-1,0,len(keys)-2)); a=(x-keys[i])/(keys[i+1]-keys[i])
    return Rk[i]@expm(a*logm(Rk[i].T@Rk[i+1])), Ck[i]+a*(Ck[i+1]-Ck[i])
def omega_c(t):   # 相机系角速度(rad/s)
    Ra,_=pose_at(t-0.017); Rb,_=pose_at(t+0.017); return logm(Ra.T@Rb)/0.034
E=json.load(open(SP+'/wobble/stats/extrinsic_from_arkit.json')); Rbc=wob.qmat(np.array([E['q_bc']]))[0]
imu=wob.load_imu(sc)
def skew(t): return np.array([[0,-t[2],t[1]],[t[2],0,-t[0]],[-t[1],t[0],0]])
data=[]
for p in PR:
    if p[4]<3.0: continue
    i=int(p[0]); s=(pid==i)&np.isfinite(z)&(z>0)&(zb>0)&(ea<4)&(eb<4)
    if s.sum()<30: continue
    ta=near(keys,int(round(p[1]*1e9))); tb=near(keys,int(round(p[2]*1e9)))
    data.append(dict(ta=ta*1e-9,tb=tb*1e-9,Ka=intr[near(ik,ta)],Kb=intr[near(ik,tb)],xa=np.stack([ua[s],va[s]],1),xb=np.stack([ub[s],vb[s]],1),
                     wa=omega_c(ta*1e-9),wb=omega_c(tb*1e-9)))
def rel(d,delta=0.0,rot='arkit',Rbc_=Rbc):
    Ra,Ca=pose_at(d['ta']+delta); Rb,Cb=pose_at(d['tb']+delta)
    R,t=Rb.T@Ra, Rb.T@(Ca-Cb)
    if rot=='gyro':
        Rab=gyro_integrate(imu,d['ta']+0.0077,d['tb']+0.0077,bias=np.array(BG[sc])); R=(Rbc_.T@Rab@Rbc_).T
    return R,t/np.linalg.norm(t)
for d in data: d['R'],d['t']=rel(d)
def cost(ax,ay=None,dc=(0,0),sel=None,RS=0.0,key='R',tau=2.0):
    ay=ax if ay is None else ay; tot=0;n=0
    for d in data:
        if sel is not None and not sel(d): continue
        R=d['R'] if key=='R' else d[key+'_R']; t=d['t'] if key=='R' else d[key+'_t']
        out=[]
        for K,x,w in ((d['Ka'],d['xa'],d['wa']),(d['Kb'],d['xb'],d['wb'])):
            fx,fy,cx,cy=K; fx*=ax; fy*=ay; cx+=dc[0]; cy+=dc[1]
            nx=(x[:,0]-cx)/fx; ny=(x[:,1]-cy)/fy; f=np.stack([nx,ny,np.ones_like(nx)],1)
            if RS:
                dt=(x[:,1]/1440.0-0.5)*RS; rv=dt[:,None]*w[None,:]   # 小角:exp(ω δ) f ≈ f + (ωδ)×f
                f=f+np.cross(rv,f); f=f/f[:,2:3]
            out.append((f,fx))
        (fa,fxa),(fb,fxb)=out
        Em=skew(t)@R; Ea=fa@Em.T; Etb=fb@Em
        d2=np.sum(fb*Ea,1)**2/(Ea[:,0]**2+Ea[:,1]**2+Etb[:,0]**2+Etb[:,1]**2)*fxa*fxb
        tot+=np.sum(np.minimum(d2,tau**2)); n+=len(d2)
    return tot/max(n,1)
AL=np.arange(0.97,1.0551,0.0025)
def best(fn):
    c=np.array([fn(a) for a in AL]); i=int(np.argmin(c))
    if 0<i<len(AL)-1:
        y0,y1,y2=c[i-1],c[i],c[i+1]; return AL[i]+0.5*(y0-y2)/(y0-2*y1+y2)*(AL[1]-AL[0]), c.min()
    return AL[i], c.min()
print('==',sc,'帧对(旋转≥3°)',len(data))
a0,c0=best(lambda a:cost(a)); print('  基线(ARKit 旋转,fx=fy 同乘):α %.4f'%a0)
# ① fx/fy 分开
g=[(ax,ay,cost(ax,ay)) for ax in np.arange(a0-0.02,a0+0.0201,0.005) for ay in np.arange(a0-0.02,a0+0.0201,0.005)]
b=min(g,key=lambda r:r[2]); print('  ① fx、fy 分开:αx %.4f αy %.4f'%(b[0],b[1]))
# ② 主点放开 ±12 px
g=[(dx,dy,best(lambda a:cost(a,dc=(dx,dy)))) for dx in (-12,-6,0,6,12) for dy in (-12,-6,0,6,12)]
b=min(g,key=lambda r:r[2][1]); print('  ② 主点同时放开:最优偏移 (%+d,%+d) px 时 α %.4f'%(b[0],b[1],b[2][0]))
# ③ 按对焦状态分组
fxs=np.array([d['Ka'][0] for d in data]); q=np.percentile(fxs,[0,33,67,100])
for lo,hi in zip(q[:-1],q[1:]):
    sel=lambda d,lo=lo,hi=hi: lo<=d['Ka'][0]<=hi and abs(d['Ka'][0]-d['Kb'][0])<3
    a,_=best(lambda a:cost(a,sel=sel)); print('  ③ 报的 fx ∈ [%.0f,%.0f](两帧 fx 差<3px):α %.4f'%(lo,hi,a))
# ④ 位姿时间整体平移
for delta in (-0.012,-0.006,0.006,0.012):
    for d in data: d['s_R'],d['s_t']=rel(d,delta)
    a,_=best(lambda a:cost(a,key='s')); print('  ④ 位姿取 t%+.0f ms:α %.4f'%(delta*1e3,a))
# ⑤ 卷帘快门
for ro in (-0.03,-0.015,0.015,0.03):
    a,c=best(lambda a:cost(a,RS=ro)); print('  ⑤ 卷帘读出 %+.0f ms(逐行 × ARKit 角速度):α %.4f 代价 %.4f(无卷帘 %.4f)'%(ro*1e3,a,c,c0))
# ⑥ 陀螺旋转 + 外参扰动
for d in data: d['g_R'],d['g_t']=rel(d,rot='gyro')
a,_=best(lambda a:cost(a,key='g')); print('  ⑥ 陀螺旋转(外参=ARKit 反推):α %.4f'%a)
for ax in range(3):
    v=np.zeros(3); v[ax]=np.radians(0.68); Rp=Rbc@expm(v)
    for d in data: d['p_R'],d['p_t']=rel(d,rot='gyro',Rbc_=Rp)
    a,_=best(lambda a:cost(a,key='p')); print('     外参绕轴 %d 转 0.68°:α %.4f'%(ax,a))
# ⑦ 旋转角之比
r=[np.linalg.norm(logm(d['g_R']))/np.linalg.norm(logm(d['R'])) for d in data]
print('  ⑦ 陀螺/ARKit 相对旋转角之比 中位 %.4f(IQR %.4f)'%(np.median(r),np.subtract(*np.percentile(r,[75,25]))))
