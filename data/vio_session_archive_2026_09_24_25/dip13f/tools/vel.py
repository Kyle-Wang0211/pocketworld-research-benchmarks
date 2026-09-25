#!/usr/bin/env python3
"""velocity of the backend's newest state vs ARKit (world-aligned by global Sim3 rotation), ba, imu_gn."""
import sys,json,numpy as np,importlib.util
spec=importlib.util.spec_from_file_location('tj','/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/dip13f/tools/traj.py'); tj=importlib.util.module_from_spec(spec); spec.loader.exec_module(tj); se=tj.se
log,cam=sys.argv[1],sys.argv[2]; step=float(sys.argv[3]) if len(sys.argv)>3 else 0.5
t,X,Y=tj.load_pair(cam); s,R,tt,_=se.sim3(X,Y)
tr,Pr,Qr=se.load_full(tj.REF); T0=tr[0]; v=se.valid_ref_mask(Pr,Qr); tr,Pr=tr[v],Pr[v]
# ARKit velocity by central difference over +-2 frames
vr=np.gradient(Pr,tr,axis=0)
from scipy.ndimage import uniform_filter1d
vr=uniform_filter1d(vr,5,axis=0)
ev=[json.loads(l) for l in open(log)]
La=[d for d in ev if d['ev']=='latest']; G={round(d['t'],4):d for d in ev if d['ev']=='imu_gn'}
K={round(d['t'],4):d for d in ev if d['ev']=='kfdec'}; L={round(d['t'],4):d for d in ev if d['ev']=='loc'}
Wn={round(d['t'],4):d for d in ev if d['ev']=='win'}
rows=[]
for d in La:
    tv=d['t']; 
    if tv<tr[0] or tv>tr[-1]: continue
    ve=R@np.array(d['v'])  # into ARKit world (no scale: velocity in XRSLAM metres)
    va=np.array([np.interp(tv,tr,vr[:,k]) for k in range(3)])
    g=G.get(round(tv,4),{}); k=K.get(round(tv,4),{}); l=L.get(round(tv,4),{}); w=Wn.get(round(tv,4),{})
    rows.append((tv-T0,np.linalg.norm(ve),np.linalg.norm(va),np.linalg.norm(ve-va),np.dot(ve,va)/max(np.dot(va,va),1e-9),d['ba'],g.get('ds',np.nan),g.get('ds_v',np.nan),g.get('sd',np.nan),k.get('mapped',-1),l.get('in3',-1),l.get('n',-1),w.get('rej_rpe',-1),w.get('nrep',-1)))
print('k_global %.4f'%(1/s))
print('  t    |v_sw| |v_ark| |dv|  proj  | ba(x,y,z)              | imu_gn ds  ds_v  sd  | mapped in3/n rejR nrep')
for a in np.arange(0,30,step):
    rr=[r for r in rows if a<=r[0]<a+step]
    if not rr: continue
    m=lambda i: np.median([r[i] for r in rr])
    ba=np.median([r[5] for r in rr],axis=0)
    print(f"{a:5.1f} {m(1):6.3f} {m(2):6.3f} {m(3):5.3f} {m(4):5.2f} | {ba[0]:+.3f} {ba[1]:+.3f} {ba[2]:+.3f} | {m(6):+.3f} {m(7):+.3f} {m(8):.3f} | {m(9):5.0f} {m(10):3.0f}/{m(11):3.0f} {m(12):4.0f} {m(13):4.0f}")
