#!/usr/bin/env python3
"""Reflection / non-static check (bench-only LiDAR ruler): XRSLAM landmark depth (x global Sim3 k) vs ARKit sceneDepth
at the same pixel, for inliers (<3 px) vs outliers at the loc step. A virtual image (reflection in glass / glossy floor)
sits BEHIND the reflecting surface => z_xrslam/z_lidar >> 1."""
import sys,json,numpy as np
RUN='/Users/kaidongwang/Developer/viobench-recordings/run-13f53d2f-5935-4b1a-a499-4dc8367ea935/ruler_subset'
T0=254666.645033333
log,td,k=sys.argv[1],float(sys.argv[2]),float(sys.argv[3])
D={}
for ln in open(RUN+'/depth.pwvi'):
    if ln.strip(): d=json.loads(ln); D[d['t_ns']]=d
dts=np.array(sorted(D)); mm=np.memmap(RUN+'/depth.bin',dtype=np.float32,mode='r'); cm=np.memmap(RUN+'/depth_conf.bin',dtype=np.uint8,mode='r')
rows=[]
for l in open(log):
    if '"ev":"loc"' not in l: continue
    d=json.loads(l); tc=int(round((d['t']-td)*1e9))
    j=dts[np.argmin(np.abs(dts-tc))]
    if abs(j-tc)>40e6: continue  # depth frames are 1 camera frame (33 ms) off the backend frames; use smooth-depth pixels only
    m=D[j]; dep=np.asarray(mm[m['offset']//4:(m['offset']+m['len'])//4]).reshape(m['h'],m['w']); conf=np.asarray(cm[m['conf_offset']:m['conf_offset']+m['conf_len']]).reshape(m['h'],m['w'])
    for u,v,e,z,kn in d['pts']:
        uc=(u+0.5)*3-0.5; vc=(v+0.5)*3-0.5
        ud=int(round((uc+0.5)*m['w']/m['image_w']-0.5)); vd=int(round((vc+0.5)*m['h']/m['image_h']-0.5))
        if 3<=ud<m['w']-3 and 3<=vd<m['h']-3 and conf[vd,ud]==2 and dep[vd,ud]>0:
            nb=dep[vd-3:vd+4,ud-3:ud+4]
            if (nb.max()-nb.min())/np.median(nb)>0.10 or (conf[vd-3:vd+4,ud-3:ud+4]<2).any(): continue
            rows.append((d['t']-td-T0,e,z*k/dep[vd,ud]))
A=np.array(rows); print('points with high-confidence LiDAR:',len(A))
for lab,(a,b) in {'all':(0,99),'dip 8-15':(8,15),'hi 22.5-26.5':(22.5,26.5)}.items():
    m=(A[:,0]>=a)&(A[:,0]<b)
    for nm,sel in [('inlier<3px',A[:,1]<3),('outlier>=3px',A[:,1]>=3)]:
        r=A[m&sel,2]
        if len(r)<5: print(f"  {lab:12s} {nm:13s} n={len(r)}"); continue
        print(f"  {lab:12s} {nm:13s} n={len(r):5d}  ratio z_vio/z_lidar median {np.median(r):.3f}  IQR [{np.percentile(r,25):.3f},{np.percentile(r,75):.3f}]  frac>1.3 {np.mean(r>1.3):.3f}  frac<0.77 {np.mean(r<0.77):.3f}")
