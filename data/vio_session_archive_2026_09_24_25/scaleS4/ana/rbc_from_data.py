import sys, os, numpy as np
sys.path.insert(0,'ana')
from acc_consistency import quat2R, logSO3, load_tum
from acc_scale2 import bandpass, interp_rot
R=os.path.expanduser('~/Developer/viobench-recordings/')
Rnom=np.array([[0,-1,0],[-1,0,0],[0,0,-1.]])   # R_bc (cv camera -> body), upstream
F=np.diag([1,-1,-1.])                            # ARKit cam -> cv cam axes
def R2q(Rm):  # -> xyzw
    w=np.sqrt(max(0,1+np.trace(Rm)))/2
    if w>1e-6:
        return np.array([(Rm[2,1]-Rm[1,2])/(4*w),(Rm[0,2]-Rm[2,0])/(4*w),(Rm[1,0]-Rm[0,1])/(4*w),w])
    x=np.sqrt(max(0,1+Rm[0,0]-Rm[1,1]-Rm[2,2]))/2
    return np.array([x,(Rm[0,1]+Rm[1,0])/(4*x),(Rm[0,2]+Rm[2,0])/(4*x),(Rm[2,1]-Rm[1,2])/(4*x)])
out={}
for run in sys.argv[1:]:
    d=np.genfromtxt(R+run+'/imu.csv',delimiter=',',skip_header=1); ti=d[:,0]*1e-9; w=d[:,1:4]
    t,p,q=load_tum(R+run+'/arkit_poses.tum')
    dt=0.01; tg=np.arange(max(t[0],ti[0])+1, min(t[-1],ti[-1])-1, dt)
    Rg=interp_rot(t, quat2R(q/np.linalg.norm(q,axis=1,keepdims=True)), tg)
    wb=logSO3(np.einsum('nji,njk->nik',Rg[:-1],Rg[1:]))/dt; wb=np.vstack([wb,wb[-1:]])   # ARKit-cam frame
    wc=wb@F.T   # cv-cam frame
    best=None
    for lag in np.arange(-20,21,0.5)*1e-3:
        wi=np.stack([np.interp(tg+lag,ti,w[:,j]) for j in range(3)],1)
        A=bandpass(wc,dt,0.05,8); B=bandpass(wi,dt,0.05,8)
        H=A.T@B; U,S,Vt=np.linalg.svd(H); D=np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))]); Rbc=Vt.T@D@U.T
        r=np.sqrt(np.mean(np.sum((B-A@Rbc.T)**2,1)))
        if best is None or r<best[0]: best=(r,lag,Rbc,A,B)
    r,lag,Rbc,A,B=best
    dev=logSO3(Rnom.T@Rbc)   # deviation expressed in camera frame (right-multiplied)
    # gyro scale check: |B| vs |A Rbc^T|
    gs=np.sum(np.sum(B*(A@Rbc.T),1))/np.sum(np.sum((A@Rbc.T)**2,1))
    # bootstrap over 4 segments
    segs=[]
    for idx in np.array_split(np.arange(len(tg)),4):
        H=A[idx].T@B[idx]; U,S,Vt=np.linalg.svd(H); D=np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))]); Rs=Vt.T@D@U.T
        segs.append(np.degrees(logSO3(Rnom.T@Rs)))
    segs=np.array(segs)
    print(f'{run[4:12]} gyro lag {lag*1e3:+.1f}ms rms {r:.4f} | dev(cam frame, deg) {np.round(np.degrees(dev),2)} |dev| {np.degrees(np.linalg.norm(dev)):.2f} | gyro/ARKit rate ratio {gs:.4f}')
    print(f'          per-quarter dev: '+' ; '.join(str(np.round(s,2)) for s in segs), ' | q_bc(data) xyzw', np.round(R2q(Rbc),7))
    out[run]=R2q(Rbc)
np.save('ana/qbc_data.npy', out, allow_pickle=True)
