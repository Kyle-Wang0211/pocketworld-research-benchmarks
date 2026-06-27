import struct,numpy as np,re,sys,os
np.random.seed(0)
def load(p):
    if p.endswith('.txt'):  # COLMAP points3D.txt: ID X Y Z R G B ERROR TRACK...
        pts=[]
        for line in open(p):
            if line.startswith('#') or not line.strip(): continue
            v=line.split(); pts.append((float(v[1]),float(v[2]),float(v[3])))
        return np.array(pts,np.float32)
    f=open(p,'rb');h=b''
    while b'end_header' not in h:h+=f.readline()
    n=int(re.search(rb'element vertex (\d+)',h).group(1));P=np.empty((n,3),np.float32)
    for i in range(n):P[i]=struct.unpack('<fff',f.read(15)[:12])
    return P
def fitS(pts):
    A=np.c_[2*pts,np.ones(len(pts))];b=(pts**2).sum(1);c,*_=np.linalg.lstsq(A,b,rcond=None);ctr=c[:3];return ctr,np.sqrt(max(1e-9,c[3]+(ctr**2).sum()))
def measure(p):
    P=load(p);n=len(P)
    span=np.percentile(np.linalg.norm(P-np.median(P,0),axis=1),90)
    sub=P[np.random.choice(n,min(20000,n),replace=False)];best=None;bn=0
    for _ in range(2500):
        ix=np.random.choice(len(sub),4,replace=False)
        try:ctr,rad=fitS(sub[ix])
        except:continue
        if not(span*0.02<rad<span*0.30):continue
        d=np.abs(np.linalg.norm(sub-ctr,axis=1)-rad);s=int((d<0.06*rad).sum())
        if s>bn:bn=s;best=(ctr,rad)
    ctr,rad=best
    for _ in range(4):
        d=np.abs(np.linalg.norm(P-ctr,axis=1)-rad);inl=d<0.06*rad;ctr,rad=fitS(P[inl])
    d=np.abs(np.linalg.norm(P-ctr,axis=1)-rad);gi=d<0.08*rad;gstd=d[gi].std()
    best=None;bn=0
    for _ in range(4000):
        ix=np.random.choice(n,3,replace=False);p0,p1,p2=P[ix]
        nrm=np.cross(p1-p0,p2-p0);ln=np.linalg.norm(nrm)
        if ln<1e-9:continue
        nrm/=ln;dist=np.abs((P-p0)@nrm);s=int((dist<0.01*span).sum())
        if s>bn:bn=s;best=(nrm,p0)
    nrm,p0=best
    for _ in range(4):
        dist=np.abs((P-p0)@nrm);inl=dist<0.01*span;Q=P[inl];c=Q.mean(0);u,sv,vt=np.linalg.svd(Q-c);nrm=vt[2];p0=c
    dist=np.abs((P-p0)@nrm);pi=dist<0.02*span;pstd=dist[pi].std()
    return n,gstd,100*gstd/span,pstd,100*pstd/span
for p in sys.argv[1:]:
    if not os.path.exists(p):print(f'{os.path.basename(p):28s} 无文件');continue
    n,gstd,gpct,pstd,ppct=measure(p)
    print(f'{os.path.basename(p):28s} 点{n:6d} 地球仪壳={gstd:.4f}({gpct:.2f}%span) 地板={pstd:.4f}({ppct:.2f}%span)')
