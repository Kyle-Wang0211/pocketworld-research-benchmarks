"""Accelerometer-vs-trajectory scale ruler (after Mustaniemi et al., arXiv 1611.09498: match visual vs inertial
accelerations at low frequency, <=1.2 Hz).  World-frame, band-limited LS:
   BP[ R_w,imu(t) f(t) ]  =  s * BP[ a_w(t) ]  + BP[ R_w,imu(t) ] b          (g*up removed by the band-pass)
R_w,imu(t) = R_wc(t) R_ic^T, R_ic from Kabsch(gyro, trajectory angular velocity) with best gyro lag.
s = how much the trajectory must be scaled to match the accelerometer (s>1: trajectory too small)."""
import sys, os, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from acc_consistency import quat2R, logSO3, load_tum
def bandpass(x, dt, lo, hi):
    n=len(x); N=1<<int(np.ceil(np.log2(2*n)))
    X=np.fft.rfft(x-x.mean(0), n=N, axis=0); f=np.fft.rfftfreq(N, dt)
    H=((f>=lo)&(f<=hi)).astype(float)
    # smooth edges (raised cosine 0.05 Hz)
    for e,sgn in ((lo,1),(hi,-1)):
        k=np.abs(f-e)<0.05; H[k]=0.5*(1+np.cos(np.pi*(f[k]-e)/0.05*(-sgn)+0))  if False else H[k]
    return np.fft.irfft(X*H[:,None], n=N, axis=0)[:n]
def interp_rot(t, Rw, tg):
    idx=np.clip(np.searchsorted(t,tg)-1,0,len(t)-2); al=(tg-t[idx])/(t[idx+1]-t[idx])
    rv=logSO3(np.einsum('nji,njk->nik',Rw[idx],Rw[idx+1]))*al[:,None]
    th=np.linalg.norm(rv,axis=1); k=rv/np.maximum(th,1e-12)[:,None]
    K=np.zeros((len(tg),3,3)); K[:,0,1]=-k[:,2];K[:,0,2]=k[:,1];K[:,1,0]=k[:,2];K[:,1,2]=-k[:,0];K[:,2,0]=-k[:,1];K[:,2,1]=k[:,0]
    return Rw[idx]@(np.eye(3)+np.sin(th)[:,None,None]*K+(1-np.cos(th))[:,None,None]*(K@K))
def ruler(ti, w, a, t, p, q, lo=0.1, hi=1.2, trim=1.0, scale_traj=1.0, tmax=None, spl=None, verbose=True, label=''):
    dt=0.01
    t0=max(t[0],ti[0])+trim; t1=min(t[-1],ti[-1])-trim
    if tmax: t1=min(t1,t0+tmax)
    tg=np.arange(t0,t1,dt)
    # positions: cubic interpolation via np.interp on a fine basis is ok for <=1.2Hz band
    pg=np.stack([np.interp(tg,t,p[:,j]) for j in range(3)],1)*scale_traj
    Rg=interp_rot(t, quat2R(q/np.linalg.norm(q,axis=1,keepdims=True)), tg)
    # accel of trajectory: second difference then band-limit (band-limit makes differentiation benign)
    aw=np.gradient(np.gradient(pg,dt,axis=0),dt,axis=0)
    wb=logSO3(np.einsum('nji,njk->nik',Rg[:-1],Rg[1:]))/dt; wb=np.vstack([wb,wb[-1:]])
    best=None
    for lag in np.arange(-30,31,1)*1e-3:
        wi=np.stack([np.interp(tg+lag,ti,w[:,j]) for j in range(3)],1)
        A=bandpass(wb,dt,0.05,5.0); B=bandpass(wi,dt,0.05,5.0)
        H=A.T@B; U,S,Vt=np.linalg.svd(H); D=np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))]); Ric=Vt.T@D@U.T
        r=np.sqrt(np.mean(np.sum((B-A@Ric.T)**2,1)))
        if best is None or r<best[0]: best=(r,lag,Ric)
    _,lag_g,Ric=best
    Rwi=np.einsum('nij,kj->nik',Rg,Ric)   # R_w,imu = R_wc R_ic^T
    fi=np.stack([np.interp(tg+lag_g,ti,a[:,j]) for j in range(3)],1)
    fw=np.einsum('nij,nj->ni',Rwi,fi)
    Y=bandpass(fw,dt,lo,hi); X=bandpass(aw,dt,lo,hi)
    Bb=[bandpass(Rwi[:,:,j],dt,lo,hi) for j in range(3)]
    if TILT:
        # small-angle correction of R_ic:  R_wi (I+[d]x) f = fw - R_wi [f]x d
        for j in range(3):
            e=np.zeros(3); e[j]=1
            Bb.append(bandpass(-np.einsum('nij,nj->ni',Rwi,np.cross(fi,e)),dt,lo,hi))
    m=slice(int(2/dt), len(tg)-int(2/dt))   # drop FFT edge effects
    A=np.stack([X[m].ravel()]+[b[m].ravel() for b in Bb],1); y=Y[m].ravel()
    x,*_=np.linalg.lstsq(A,y,rcond=None); s=x[0]
    dtilt=np.degrees(np.linalg.norm(x[4:7])) if TILT else 0.0
    # amplitude-ratio (errors-in-variables-free check): rms(Y - bias part)/rms(X)
    yb=y-A[:,1:]@x[1:]; ratio=np.sqrt(np.mean(yb**2)/np.mean(A[:,0]**2))
    corr=np.corrcoef(A[:,0],yb)[0,1]
    # segments
    segs=[]
    if spl:
        idx=np.arange(len(tg))[m]
        for sidx in np.array_split(idx,spl):
            A2=np.stack([X[sidx].ravel()]+[b[sidx].ravel() for b in Bb],1); xx,*_=np.linalg.lstsq(A2,Y[sidx].ravel(),rcond=None); segs.append(xx[0])
    if verbose:
        print(f'{label:30s} band {lo}-{hi}Hz gyro-lag {lag_g*1e3:+.0f}ms | LS s={s:.4f}  amp-ratio {ratio:.4f}  corr {corr:.3f}  rms|a_traj| {np.sqrt(np.mean(A[:,0]**2)):.3f} m/s2  bias {np.round(x[1:4],3)} dRic {dtilt:.2f}deg'+(f' | seg s: {" ".join(f"{v:.3f}" for v in segs)}' if segs else ''))
    return dict(s=s, ratio=ratio, corr=corr, lag=lag_g, segs=segs)
TILT=True
REC=os.path.expanduser('~/Developer/viobench-recordings/')
def load_imu_run(run):
    d=np.genfromtxt(REC+run+'/imu.csv',delimiter=',',skip_header=1); return d[:,0]*1e-9, d[:,1:4], d[:,4:7]
def load_imu_euroc(path):
    d=np.genfromtxt(path,delimiter=',',skip_header=1); return d[:,0]*1e-9, d[:,1:4], d[:,4:7]
if __name__=='__main__':
    mode=sys.argv[1]
    if mode=='run':
        run,tum=sys.argv[2],sys.argv[3]; lab=sys.argv[4] if len(sys.argv)>4 else ''
        ti,w,a=load_imu_run(run); t,p,q=load_tum(tum)
        for lo,hi in ((0.1,1.2),(0.2,2.0),(0.1,0.8)):
            ruler(ti,w,a,t,p,q,lo,hi,label=lab,spl=4 if (lo,hi)==(0.1,1.2) else None)
    elif mode=='euroc':
        ti,w,a=load_imu_euroc(sys.argv[2]); t,p,q=load_tum(sys.argv[3]); lab=sys.argv[4] if len(sys.argv)>4 else ''
        for lo,hi in ((0.1,1.2),(0.2,2.0),(0.1,0.8)):
            ruler(ti,w,a,t,p,q,lo,hi,label=lab,spl=4 if (lo,hi)==(0.1,1.2) else None)
