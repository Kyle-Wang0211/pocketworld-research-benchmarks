"""Is a trajectory's metric scale consistent with the raw accelerometer it came with?
f_imu(t+tau) = R_ic R_wc(t)^T (s*a_w(t) + g*up) + b + lever(r)     (linear LS in s,g,b,r)
R_ic from gyro vs trajectory angular velocity (Kabsch). Same SG filter on both sides."""
import sys, os, numpy as np
R = os.path.expanduser('~/Developer/viobench-recordings/')
def quat2R(q):  # x y z w
    x,y,z,w = q.T
    return np.stack([np.stack([1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],-1),
                     np.stack([2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],-1),
                     np.stack([2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],-1)],-2)
def logSO3(Rm):
    c = np.clip((np.trace(Rm,axis1=-2,axis2=-1)-1)/2,-1,1); th=np.arccos(c)
    v = np.stack([Rm[...,2,1]-Rm[...,1,2], Rm[...,0,2]-Rm[...,2,0], Rm[...,1,0]-Rm[...,0,1]],-1)
    k = np.where(th<1e-8, 0.5, th/(2*np.sin(np.maximum(th,1e-12))))
    return v*k[...,None]
def sg_coeffs(win, order, deriv, dt):
    half=win//2; x=np.arange(-half,half+1)*dt
    A=np.vander(x,order+1,increasing=True); P=np.linalg.pinv(A)
    import math
    return P[deriv]*math.factorial(deriv)
def sg(x, win, order, deriv, dt):
    c=sg_coeffs(win,order,deriv,dt)[::-1]
    return np.stack([np.convolve(x[:,j],c,mode='same') for j in range(x.shape[1])],1)
def load_tum(p):
    d=np.loadtxt(p); 
    t=d[:,0]; 
    if t[0]>1e12: t=t*1e-9
    return t, d[:,1:4], d[:,4:8]
def analyse(run, tum, yup=True, label='', win_s=0.25, taus=np.arange(-40,41,2), seg=4):
    imu=np.genfromtxt(R+run+'/imu.csv',delimiter=',',skip_header=1)
    ti=imu[:,0]*1e-9; w=imu[:,1:4]; a=imu[:,4:7]
    t,p,q=load_tum(tum)
    # uniform grid 100Hz over overlap
    dt=0.01; tg=np.arange(max(t[0],ti[0])+0.3, min(t[-1],ti[-1])-0.3, dt)
    # interpolate trajectory positions (60Hz) linearly onto grid -> fine for SG smoothing with 0.25s window
    pg=np.stack([np.interp(tg,t,p[:,j]) for j in range(3)],1)
    # rotation: nearest+slerp via small-angle interpolation
    Rw=quat2R(q/np.linalg.norm(q,axis=1,keepdims=True))
    idx=np.clip(np.searchsorted(t,tg)-1,0,len(t)-2); al=(tg-t[idx])/(t[idx+1]-t[idx])
    dR=np.einsum('nji,njk->nik',Rw[idx],Rw[idx+1]); 
    rv=logSO3(dR)*al[:,None]
    th=np.linalg.norm(rv,axis=1,keepdims=True); k=rv/np.maximum(th,1e-12)
    K=np.zeros((len(tg),3,3)); K[:,0,1]=-k[:,2];K[:,0,2]=k[:,1];K[:,1,0]=k[:,2];K[:,1,2]=-k[:,0];K[:,2,0]=-k[:,1];K[:,2,1]=k[:,0]
    Rexp=np.eye(3)+np.sin(th)[:,:,None]*K+(1-np.cos(th))[:,:,None]*(K@K)
    Rg=Rw[idx]@Rexp
    W=int(round(win_s/dt))|1
    acc_w=sg(pg,W,3,2,dt)
    # body angular velocity from trajectory
    wb=logSO3(np.einsum('nji,njk->nik',Rg[:-1],Rg[1:]))/dt; wb=np.vstack([wb,wb[-1:]])
    wb_s=sg(wb,W,3,0,dt); wdot=sg(wb,W,3,1,dt)
    up=np.array([0,1.0,0]) if yup else np.array([0,0,1.0])
    out=[]
    for tau in taus:
        tt=tg+tau*1e-3
        wi=np.stack([np.interp(tt,ti,w[:,j]) for j in range(3)],1); wi_s=sg(wi,W,3,0,dt)
        ai=np.stack([np.interp(tt,ti,a[:,j]) for j in range(3)],1); ai_s=sg(ai,W,3,0,dt)
        m=slice(W,len(tg)-W)
        # Kabsch: wi = R_ic wb
        H=wb_s[m].T@wi_s[m]; U,S,Vt=np.linalg.svd(H); D=np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))]); Ric=Vt.T@D@U.T
        gres=np.sqrt(np.mean(np.sum((wi_s[m]-wb_s[m]@Ric.T)**2,1)))
        out.append((tau,gres,Ric))
    gi=int(np.argmin([o[1] for o in out])); tau_g=out[gi][0]; Ric=out[gi][2]
    res=[]
    for tau in taus:
        tt=tg+tau*1e-3
        ai=np.stack([np.interp(tt,ti,a[:,j]) for j in range(3)],1); ai_s=sg(ai,W,3,0,dt)
        m=np.arange(W,len(tg)-W)
        # model in IMU frame: f = Ric Rg^T (s a_w + g up) + b + Ric(wdot x r + w x (w x r))  [r in traj-body frame]
        RT=np.einsum('ij,nkj->nik',Ric,Rg)  # Ric Rg^T
        c_s=np.einsum('nij,nj->ni',RT,acc_w); c_g=np.einsum('nij,j->ni',RT,up)
        cols=[c_s[m],c_g[m]]
        for j in range(3):
            e=np.zeros(3); e[j]=1; cols.append(np.tile(e,(len(m),1)))
        for j in range(3):
            e=np.zeros(3); e[j]=1
            lv=np.cross(wdot[m],e)+np.cross(wb_s[m],np.cross(wb_s[m],e))
            cols.append(lv@Ric.T)
        A=np.stack([c.ravel() for c in cols],1); y=ai_s[m].ravel()
        x,*_=np.linalg.lstsq(A,y,rcond=None); r=y-A@x
        res.append((tau,np.sqrt(np.mean(r**2)),x))
    ai_=int(np.argmin([r[1] for r in res])); tau_a,rms,x=res[ai_]
    s,g=x[0],x[1]
    # segment spread at best tau (refit per segment)
    tt=tg+tau_a*1e-3
    ai=np.stack([np.interp(tt,ti,a[:,j]) for j in range(3)],1); ai_s=sg(ai,W,3,0,dt)
    RT=np.einsum('ij,nkj->nik',Ric,Rg); c_s=np.einsum('nij,nj->ni',RT,acc_w); c_g=np.einsum('nij,j->ni',RT,up)
    segs=[]
    allm=np.arange(W,len(tg)-W)
    for sidx in np.array_split(allm,seg):
        cols=[c_s[sidx],c_g[sidx]]+[np.tile(np.eye(3)[j],(len(sidx),1)) for j in range(3)]
        for j in range(3):
            e=np.eye(3)[j]; lv=np.cross(wdot[sidx],e)+np.cross(wb_s[sidx],np.cross(wb_s[sidx],e)); cols.append(lv@Ric.T)
        A=np.stack([c.ravel() for c in cols],1); xx,*_=np.linalg.lstsq(A,ai_s[sidx].ravel(),rcond=None); segs.append(xx[0]/xx[1]*9.80)
    ang=np.degrees(np.arccos(np.clip((np.trace(Ric)-1)/2,-1,1)))
    # deviation of Ric from nearest signed permutation
    P=np.zeros((3,3)); 
    for i in range(3): j=np.argmax(np.abs(Ric[i])); P[i,j]=np.sign(Ric[i,j])
    dev=np.degrees(np.linalg.norm(logSO3(P.T@Ric)))
    print(f'{label:34s} tau_gyro {tau_g:+4.0f}ms  gyro-fit rms {out[gi][1]:.3f} rad/s | tau_acc {tau_a:+4.0f}ms rms {rms:.3f} | s={s:.4f} g={g:.4f}  s/(g/9.80)={s/g*9.80:.4f}  lever r={np.round(x[5:8]*100,1)}cm b={np.round(x[2:5],3)}')
    print(f'{"":34s} per-segment s_rel: {" ".join(f"{v:.3f}" for v in segs)} | R_ic dev from signed perm {dev:.2f} deg')
    return dict(s=s,g=g,srel=s/g*9.80,tau_g=tau_g,tau_a=tau_a,segs=segs,Ric=Ric,dev=dev)
if __name__=='__main__':
    run=sys.argv[1]; tum=sys.argv[2]; lab=sys.argv[3] if len(sys.argv)>3 else os.path.basename(tum)
    yup = ('--zup' not in sys.argv)
    analyse(run,tum,yup,lab)
