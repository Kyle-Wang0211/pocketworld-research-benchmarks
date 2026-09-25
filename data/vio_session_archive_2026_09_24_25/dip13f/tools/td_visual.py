#!/usr/bin/env python3
"""Independent (non-XRSLAM) camera-IMU time offset: frame-to-frame rotation from image tracks (LK + essential
matrix with the per-frame ARKit K, 640 box/3 like the replay) vs gyro. Model: omega_cam(t_frame_mid + td) ~ R_cb*gyro.
Grid over td; the camera->body rotation is re-fitted (Kabsch) at each td so a wrong nominal extrinsic cannot bias it.
td > 0  <=> image content happens LATER than the recorded frame timestamp (XRSLAM cam0.time_offset convention)."""
import sys,json,numpy as np,cv2
from scipy.spatial.transform import Rotation as Rr
run=sys.argv[1]
off={}
for ln in open(run+'/frames.pwvi'):
    if ln.strip(): d=json.loads(ln); off[d['frame']]=d['offset']
rows=[l.strip().split(',') for l in open(run+'/camera_index.csv').readlines()[1:] if l.strip()]
K={}
for l in open(run+'/intrinsics.jsonl'):
    d=json.loads(l); K[round(d['t'],4)]=d['intrinsics_fxfycxcy']
mm=np.memmap(run+'/frames.bin',dtype=np.uint8,mode='r')
def img(fr):
    full=np.asarray(mm[off[fr]:off[fr]+1920*1440]).reshape(1440,1920)
    return np.rint(full.reshape(480,3,640,3).astype(np.float32).mean(axis=(1,3))).astype(np.uint8)
def Kof(ts):
    k=K[round(int(ts)*1e-9,4)] if round(int(ts)*1e-9,4) in K else None
    if k is None: return None
    fx,fy,cx,cy=k; return np.array([[fx/3,0,(cx+.5)/3-.5],[0,fy/3,(cy+.5)/3-.5],[0,0,1]])
tm=[];wv=[];nin=[]
prev=None
for ts,fr in rows:
    fr=int(fr); t=int(ts)*1e-9; Km=Kof(ts)
    im=img(fr)
    if prev is not None and Km is not None:
        pt,pim,pK=prev
        p0=cv2.goodFeaturesToTrack(pim,400,0.01,12)
        if p0 is not None and len(p0)>=30:
            p1,st,_=cv2.calcOpticalFlowPyrLK(pim,im,p0,None,winSize=(21,21),maxLevel=3)
            pb,st2,_=cv2.calcOpticalFlowPyrLK(im,pim,p1,None,winSize=(21,21),maxLevel=3)
            good=(st[:,0]==1)&(st2[:,0]==1)&(np.linalg.norm((pb-p0)[:,0],axis=1)<0.5)
            if good.sum()>=30:
                a=cv2.undistortPoints(p0[good],pK,None)[:,0]; b=cv2.undistortPoints(p1[good],Km,None)[:,0]
                E,m=cv2.findEssentialMat(a,b,np.eye(3),cv2.RANSAC,0.999,1.0/450)
                if E is not None and E.shape==(3,3):
                    n,R,tt,m2=cv2.recoverPose(E,a,b,np.eye(3),mask=m)
                    if n>=30:
                        # R maps prev-camera coords to current-camera coords: x1 = R x0 + t  => camera rotated by R^T
                        wv.append(Rr.from_matrix(R.T).as_rotvec()/(t-pt)); tm.append((t+pt)/2); nin.append(n)
    prev=(t,im,Km)
tm=np.array(tm); wv=np.array(wv)
I=np.loadtxt(run+'/imu.csv',delimiter=',',skiprows=1); ti=I[:,0]*1e-9; g=I[:,1:4]
dtf=np.median(np.diff(tm))
def gyro_avg(tq,d,h):
    s=np.zeros((len(tq),3)); us=np.linspace(-h,h,9)
    for u in us: s+=np.stack([np.interp(tq+d+u,ti,g[:,k]) for k in range(3)],1)
    return s/len(us)
res=[]
mag=np.linalg.norm(wv,axis=1); sel=mag>np.radians(5)   # only frames with real rotation carry td information
for d in np.arange(-0.030,0.0301,0.0005):
    G=gyro_avg(tm[sel],d,dtf/2)
    H=G.T@wv[sel]; U,S,Vt=np.linalg.svd(H); D=np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))]); Rm=Vt.T@D@U.T
    r=wv[sel]-(Rm@G.T).T; res.append((d,np.sqrt(np.median((r**2).sum(1)))))
res=np.array(res); i=np.argmin(res[:,1])
print('pairs',len(tm),'used (|w|>5deg/s)',sel.sum(),'median inliers',int(np.median(nin)))
for d,r in res[::4]: print(f"  td {d*1000:+6.1f} ms  median|res| {np.degrees(r):.3f} deg/s")
y0,y1,y2=res[i-1,1],res[i,1],res[i+1,1]; o=0.5*(y0-y2)/(y0-2*y1+y2)
print('BEST td = %+.2f ms'%((res[i,0]+o*0.0005)*1000))
# half-split stability
for lab,m in [('first half',tm<np.median(tm)),('second half',tm>=np.median(tm))]:
    rr=[]
    for d in np.arange(-0.030,0.0301,0.0005):
        mm_=sel&m; G=gyro_avg(tm[mm_],d,dtf/2); H=G.T@wv[mm_]; U,S,Vt=np.linalg.svd(H); D=np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))]); Rm=Vt.T@D@U.T
        r=wv[mm_]-(Rm@G.T).T; rr.append((d,np.sqrt(np.median((r**2).sum(1)))))
    rr=np.array(rr); print(' ',lab,'best td %+.1f ms'%(rr[np.argmin(rr[:,1]),0]*1000))
