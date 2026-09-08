import sys, numpy as np
def load(p):
    T,P=[],[]
    for ln in open(p):
        ln=ln.strip()
        if not ln or ln.startswith('#'): continue
        f=ln.split()
        if len(f)<8: continue
        T.append(float(f[0])); P.append([float(f[1]),float(f[2]),float(f[3])])
    return np.array(T), np.array(P)
def umeyama(X,Y,ws=True):
    mx,my=X.mean(1,keepdims=True),Y.mean(1,keepdims=True)
    Xc,Yc=X-mx,Y-my
    S=Yc@Xc.T/X.shape[1]
    U,D,Vt=np.linalg.svd(S); d=np.ones(3)
    if np.linalg.det(U)*np.linalg.det(Vt)<0: d[2]=-1
    R=U@np.diag(d)@Vt
    s=(D*d).sum()/((Xc**2).sum()/X.shape[1]) if ws else 1.0
    return s,R,my-s*R@mx
te,Pe=load(sys.argv[1]); tr,Pr=load(sys.argv[2])
idx=np.clip(np.searchsorted(tr,te),1,len(tr)-1)
l=np.abs(te-tr[idx-1]); r=np.abs(te-tr[idx])
pick=np.where(l<r,idx-1,idx); ok=np.minimum(l,r)<0.010
X=Pe[ok].T; Y=Pr[pick[ok]].T
s,R,t=umeyama(X,Y); e=np.linalg.norm((s*R@X+t)-Y,axis=0)
s1,R1,t1=umeyama(X,Y,False); e1=np.linalg.norm((R1@X+t1)-Y,axis=0)
print(f"  配对 {X.shape[1]} | Sim3 ATE {np.sqrt((e**2).mean())*100:.2f} cm | 尺度偏差 {abs(1-s)*100:.2f}% | SE3 ATE {np.sqrt((e1**2).mean())*100:.2f} cm")
