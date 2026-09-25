#!/usr/bin/env python3
"""Independent camera-IMU time offset (no XRSLAM): predict each LK track's next position from the GYRO rotation
integrated over [t0+td, t1+td] (nominal q_bc from the device yaml, per-frame ARKit K, 640 box/3), score the median
pixel residual over rotating frames, grid td. Translation parallax is a td-independent noise floor.
td > 0 <=> image content later than the recorded timestamp (= XRSLAM cam0.time_offset)."""
import sys,json,numpy as np,cv2
from scipy.spatial.transform import Rotation as Rr
import os; WMIN=float(os.environ.get("WMIN","10")); run=sys.argv[1]; tlo=float(sys.argv[2]) if len(sys.argv)>2 else -1; thi=float(sys.argv[3]) if len(sys.argv)>3 else 1e9
off={}
for ln in open(run+'/frames.pwvi'):
    if ln.strip(): d=json.loads(ln); off[d['frame']]=d['offset']
rows=[l.strip().split(',') for l in open(run+'/camera_index.csv').readlines()[1:] if l.strip()]
Kd={}
for l in open(run+'/intrinsics.jsonl'):
    d=json.loads(l); Kd[int(round(d['t']*1e9))]=d['intrinsics_fxfycxcy']
kt=np.array(sorted(Kd))
mm=np.memmap(run+'/frames.bin',dtype=np.uint8,mode='r')
def img(fr):
    full=np.asarray(mm[off[fr]:off[fr]+1920*1440]).reshape(1440,1920)
    return np.rint(full.reshape(480,3,640,3).astype(np.float32).mean(axis=(1,3))).astype(np.uint8)
def Kof(tn):
    j=kt[np.argmin(np.abs(kt-tn))]; fx,fy,cx,cy=Kd[j]
    return np.array([[fx/3,0,(cx+.5)/3-.5],[0,fy/3,(cy+.5)/3-.5],[0,0,1]])
I=np.loadtxt(run+'/imu.csv',delimiter=',',skiprows=1); ti=I[:,0]*1e-9; g=I[:,1:4]
Rbc=Rr.from_quat([-0.7071068,0.7071068,0,0]).as_matrix()   # camera->body
def gyro_rot(t0,t1,n=12):
    ts=np.linspace(t0,t1,n+1); R=np.eye(3)
    for a,b in zip(ts[:-1],ts[1:]):
        w=np.array([np.interp((a+b)/2,ti,g[:,k]) for k in range(3)])
        R=R@Rr.from_rotvec(w*(b-a)).as_matrix()
    return R   # body_t0 <- body_t1 orientation increment (R_wb1 = R_wb0 @ R)
T0=int(rows[0][0])*1e-9
pairs=[]; prev=None
for ts,fr in rows:
    tn=int(ts); t=tn*1e-9
    if t-T0<tlo or t-T0>thi: prev=None; continue
    im=img(int(fr)); K1=Kof(tn)
    if prev is not None:
        pt,pim,K0=prev
        p0=cv2.goodFeaturesToTrack(pim,300,0.01,15)
        if p0 is not None and len(p0)>=20:
            p1,st,_=cv2.calcOpticalFlowPyrLK(pim,im,p0,None,winSize=(21,21),maxLevel=3)
            pb,st2,_=cv2.calcOpticalFlowPyrLK(im,pim,p1,None,winSize=(21,21),maxLevel=3)
            ok=(st[:,0]==1)&(st2[:,0]==1)&(np.linalg.norm((pb-p0)[:,0],axis=1)<0.5)
            if ok.sum()>=20: pairs.append((pt,t,p0[ok,0],p1[ok,0],K0,K1))
    prev=(t,im,K1)
def score(td,conv):
    out=[]
    for t0,t1,a,b,K0,K1 in pairs:
        Rb=gyro_rot(t0+td,t1+td); Rc=Rbc.T@Rb@Rbc   # cam0 <- cam1
        if np.degrees(np.linalg.norm(Rr.from_matrix(Rc).as_rotvec()))/(t1-t0)<WMIN: continue
        M=K1@(Rc.T if conv==0 else Rc)@np.linalg.inv(K0)
        h=(M@np.c_[a,np.ones(len(a))].T).T; pr=h[:,:2]/h[:,2:3]
        out.append(np.median(np.linalg.norm(pr-b,axis=1)))
    return np.mean(out),len(out)
for conv in (0,1):
    print('convention',conv,'score@0 %.2f px'%score(0.0,conv)[0])
conv=0 if score(0.0,0)[0]<score(0.0,1)[0] else 1
res=[(d,)+score(d,conv) for d in np.arange(-0.020,0.0251,0.002)]
for d,s,n in res: print(f"  td {d*1000:+5.1f} ms  mean(median px residual) {s:.3f}  n={n}")
r=np.array([(d,s) for d,s,n in res]); i=np.argmin(r[:,1])
if 0<i<len(r)-1:
    y0,y1,y2=r[i-1,1],r[i,1],r[i+1,1]; o=0.5*(y0-y2)/(y0-2*y1+y2); print('BEST td = %+.1f ms'%((r[i,0]+o*0.002)*1000))
