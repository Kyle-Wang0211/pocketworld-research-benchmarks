#!/usr/bin/env python3
"""Independent td check: ARKit camera angular velocity (from its poses, labelled with frame timestamps) vs raw
gyro (CoreMotion clock). Finds delta maximising agreement: gyro(t + delta) ~ omega_ARKit(t).
delta > 0  <=> the ARKit frame timestamp is EARLIER than the instant ARKit's pose describes
(i.e. image content corresponds to t_frame + delta on the IMU clock) == cam0.time_offset sign convention
(XRSLAM: t_img_imu_clock = t_frame + time_offset, euroc_dataset_reader.cpp)."""
import sys,numpy as np
from scipy.spatial.transform import Rotation as Rr
run=sys.argv[1]; tmax=float(sys.argv[2]) if len(sys.argv)>2 else 1e9
a=np.loadtxt(run+'/arkit_poses.tum'); T0=a[0,0]
v=np.abs(a[:,1:4]).sum(1)>0; a=a[v]; a=a[a[:,0]-T0<tmax]
t=a[:,0]; R=Rr.from_quat(a[:,4:8])
I=np.loadtxt(run+'/imu.csv',delimiter=',',skiprows=1); ti=I[:,0]*1e-9; g=I[:,1:4]
# camera-frame angular velocity from ARKit (ARKit camera frame: x right, y up, z back)
dR=(R[:-1].inv()*R[1:]).as_rotvec(); dt=np.diff(t); wc=dR/dt[:,None]; tm=(t[:-1]+t[1:])/2
ok=(dt>0.02)&(dt<0.05); wc,tm=wc[ok],tm[ok]
# body(gyro) -> ARKit camera: fit rotation by least squares at delta=0 first, then refine per delta
def gyro_at(tq,d):
    return np.stack([np.interp(tq+d,ti,g[:,k]) for k in range(3)],1)
# boxcar the gyro over the frame interval to match the finite-difference (average) rate
def gyro_avg(tq,d,h=1/60):
    s=np.zeros((len(tq),3)); n=9
    for u in np.linspace(-h,h,n): s+=gyro_at(tq+u,d)
    return s/n
best=None; res=[]
for d in np.arange(-0.030,0.0301,0.001):
    G=gyro_avg(tm,d)
    # Kabsch rotation G->wc
    H=G.T@wc; U,S,Vt=np.linalg.svd(H); D=np.diag([1,1,np.sign(np.linalg.det(Vt.T@U.T))]); Rm=Vt.T@D@U.T
    r=wc-(Rm@G.T).T; rms=np.sqrt((r**2).sum(1).mean())
    res.append((d,rms)); 
    if best is None or rms<best[1]: best=(d,rms,Rm)
res=np.array(res)
print('delta_ms  rms(rad/s)'); 
for d,r in res[::3]: print(f"{d*1000:+6.1f}  {r:.4f}")
# parabolic refine
i=np.argmin(res[:,1]); 
if 0<i<len(res)-1:
    y0,y1,y2=res[i-1,1],res[i,1],res[i+1,1]; off=0.5*(y0-y2)/(y0-2*y1+y2)
    print('best delta = %.2f ms (grid %.1f), rms %.4f rad/s'%((res[i,0]+off*0.001)*1000,res[i,0]*1000,y1))
print('R_body->arkitcam (deg from nominal check):',np.round(Rr.from_matrix(best[2]).as_euler('xyz',degrees=True),2))
