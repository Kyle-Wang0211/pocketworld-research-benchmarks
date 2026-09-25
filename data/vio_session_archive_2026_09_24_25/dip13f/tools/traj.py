#!/usr/bin/env python3
"""dip13f trajectory diagnostics: XRSLAM camera-pose tum vs ARKit tum.
Reuses scaleS1/scale_eval.py (canonical pairing + Sim3). Prints global k, quarter k, sliding-window
local scale, per-frame step anomalies."""
import sys, json, importlib.util, numpy as np
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
spec=importlib.util.spec_from_file_location('se',SP+'/scaleS1/scale_eval.py'); se=importlib.util.module_from_spec(spec); spec.loader.exec_module(se)
REF='/Users/kaidongwang/Developer/viobench-recordings/run-13f53d2f-5935-4b1a-a499-4dc8367ea935/arkit_poses.tum'

def detect_td(est, ref=REF):
    te=se.load_full(est)[0]; tr=se.load_full(ref)[0]
    i=np.clip(np.searchsorted(tr,te),1,len(tr)-1); l=te-tr[i-1]; r=te-tr[i]
    d=np.where(np.abs(l)<np.abs(r),l,r)
    return float(np.round(np.median(d),4))  # engine output t = image t + cam0.time_offset
def load_pair(est, ref=REF, cam=False):
    td=detect_td(est,ref)
    t,X,Y=se.pair_up(est,ref,cam=cam,td=td)
    return t,X,Y

def local_scale(t,X,Y,win=2.0,step=0.5,t0=None):
    out=[]
    a=t[0]
    while a+win<=t[-1]+1e-9:
        m=(t>=a)&(t<a+win)
        if m.sum()>=20:
            Yc=Y[:,m]-Y[:,m].mean(1,keepdims=True)
            spread=float(np.sqrt((Yc**2).sum(0).mean()))
            s,_,_,ate=se.sim3(X[:,m],Y[:,m])
            # path-length ratio (alignment free)
            pe=np.linalg.norm(np.diff(X[:,m],axis=1),axis=0).sum(); pr=np.linalg.norm(np.diff(Y[:,m],axis=1),axis=0).sum()
            out.append((a,a+win,1/s,pe/pr,spread,ate))
        a+=step
    return out

if __name__=='__main__':
    est=sys.argv[1]; ref=sys.argv[2] if len(sys.argv)>2 and not sys.argv[2].startswith('-') else REF
    t,X,Y=load_pair(est,ref)
    tr,Pr,Qr=se.load_full(ref); T0=tr[0]
    e=se.estimators(X,Y,t)
    print('n',e['n'],'k_fwd %.4f sym %.4f pm %.4f ate_sim3 %.2f cm'%(e['k_sim3_fwd'],e['k_sim3_sym'],e['k_pair_med'],e['ate_sim3_cm']))
    print('quarters', [round(x,4) for x in se.segments(X,Y,t,4)], 'edges(rec t)', [round(x-T0,2) for x in np.linspace(t[0],t[-1],5)])
    s,R,tt,_=se.sim3(X,Y)
    Xa=(s*R@X+tt)
    err=np.linalg.norm(Xa-Y,axis=0)
    print('first pose rec t %.3f'%(t[0]-T0))
    if '--win' in sys.argv:
        for a,b,k,pl,sp,ate in local_scale(t,X,Y,2.0,0.5):
            print(f"  win {a-T0:6.2f}-{b-T0:6.2f}  k_sim3 {k:.3f}  pathratio {pl:.3f}  spread {sp*100:5.1f}cm ate {ate*100:4.1f}cm")
    if '--steps' in sys.argv:
        de=np.linalg.norm(np.diff(Xa,axis=1),axis=0); dr=np.linalg.norm(np.diff(Y,axis=1),axis=0)
        idx=np.where(de-dr>0.02)[0]
        for i in idx: print(f"  step {t[i+1]-T0:7.3f}  est {de[i]*100:5.2f}cm  ark {dr[i]*100:5.2f}cm  err {err[i+1]*100:5.2f}cm")
