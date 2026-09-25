#!/usr/bin/env python3
"""dip13f: engine-log timeline in 0.5 s bins (recording time), plus IMU/ARKit kinematics and local scale."""
import sys, json, numpy as np, importlib.util
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
spec=importlib.util.spec_from_file_location('tj',SP+'/dip13f/tools/traj.py'); tj=importlib.util.module_from_spec(spec); spec.loader.exec_module(tj)
se=tj.se
RUN='/Users/kaidongwang/Developer/viobench-recordings/run-13f53d2f-5935-4b1a-a499-4dc8367ea935'
def load_log(p):
    ev={}
    for l in open(p):
        try: d=json.loads(l)
        except: continue
        ev.setdefault(d['ev'],[]).append(d)
    return ev
def imu(run=RUN):
    a=np.loadtxt(run+'/imu.csv',delimiter=',',skiprows=1); a[:,0]*=1e-9; return a
def arkit(run=RUN):
    t,P,Q=se.load_full(run+'/arkit_poses.tum'); return t,P,Q
def rotvec_rate(t,Q):
    from scipy.spatial.transform import Rotation as Rr
    R=Rr.from_quat(Q); dt=np.diff(t); rv=(R[:-1].inv()*R[1:]).as_rotvec()
    return t[1:], np.linalg.norm(rv,axis=1)/dt
if __name__=='__main__':
    log=sys.argv[1]; cam=sys.argv[2]; B=float(sys.argv[3]) if len(sys.argv)>3 else 0.5
    ev=load_log(log)
    tr,Pr,Qr=arkit(); T0=tr[0]
    v=se.valid_ref_mask(Pr,Qr)
    # ARKit speed
    ts=tr[1:]; sp=np.linalg.norm(np.diff(Pr,axis=0),axis=1)/np.diff(tr); sp[~v[1:]]=np.nan
    tw,wr=rotvec_rate(tr,Qr)
    I=imu(); ti=I[:,0]; gy=np.linalg.norm(I[:,1:4],axis=1); ac=I[:,4:7]
    # acc excitation: |a| deviation from its 1-s running mean (gravity removed crudely)
    from scipy.ndimage import uniform_filter1d
    am=uniform_filter1d(ac,size=100,axis=0,mode='nearest'); aexc=np.linalg.norm(ac-am,axis=1)
    t,X,Y=tj.load_pair(cam)
    loc=tj.local_scale(t,X,Y,2.0,B)
    ft=ev['ft']; kfd=ev['kfdec']; lc=ev['loc']; wn=ev.get('win',[]); gn=ev.get('imu_gn',[]); la=ev['latest']
    def binsel(arr,key,a,b):
        return [d for d in arr if a<=d[key]-T0<b]
    edges=np.arange(0,30.0001,B)
    print(' t0-t1   | fx     | trk  tot  new  tlmed ge10 | mis°  nt% flow | kf% mapped | loc n in3  med  |dp|mm | win ntrk nrep rejR | imu_gn ds(sd) | vSW  vARK | ark v  w°/s gyro aexc | k2s')
    for a,b in zip(edges[:-1],edges[1:]):
        F=binsel(ft,'t',a,b); K=binsel(kfd,'t',a,b); L=binsel(lc,'t',a,b); Wn=binsel(wn,'t',a,b); G=binsel(gn,'t',a,b); La=binsel(la,'t',a,b)
        if not F: continue
        fx=np.mean([d['fx'] for d in F])*3
        trk=np.mean([d['n_out'] for d in F]); tot=np.mean([d['n_total'] for d in F]); new=np.mean([d['n_total']-d['n_out'] for d in F if d['sw']]) if any(d['sw'] for d in F) else 0
        tlm=np.median([d['tl_med'] for d in F]); g10=np.mean([d['tl_ge10'] for d in F])
        mis=np.median([d['misalign'] for d in F]); nt=100*np.mean([d['no_trans'] for d in F]); fl=np.median([d['flow'] for d in F])*3
        kf=100*np.mean([d['kf'] for d in K]) if K else np.nan; mp=np.mean([d['mapped'] for d in K]) if K else np.nan
        ln=np.mean([d['n'] for d in L]) if L else np.nan; li3=np.mean([d['in3']/max(d['n'],1) for d in L])*100 if L else np.nan
        lmed=np.median([d['med_px'] for d in L]) if L else np.nan; ldp=np.median([np.linalg.norm(d['dp_pred']) for d in L])*1e3 if L else np.nan
        wt=np.mean([d['ntrk'] for d in Wn]) if Wn else np.nan; wr_=np.mean([d['nrep'] for d in Wn]) if Wn else np.nan; rj=np.mean([d['rej_rpe'] for d in Wn]) if Wn else np.nan
        gds=np.median([d['ds'] for d in G]) if G else np.nan; gsd=np.median([d['sd'] for d in G]) if G else np.nan
        vsw=np.median([np.linalg.norm(d['v']) for d in La]) if La else np.nan
        m=(ts-T0>=a)&(ts-T0<b); vark=np.nanmedian(sp[m]) if m.any() else np.nan
        m2=(tw-T0>=a)&(tw-T0<b); wd=np.degrees(np.median(wr[m2])) if m2.any() else np.nan
        m3=(ti-T0>=a)&(ti-T0<b); g=np.degrees(np.median(gy[m3])); ae=np.median(aexc[m3])
        ks=[k for (aa,bb,k,pl,s_,at) in loc if abs((aa+bb)/2-T0-(a+b)/2)<B/2+1e-6]
        print(f"{a:5.1f}-{b:4.1f} |{fx:7.1f} |{trk:5.0f}{tot:5.0f}{new:5.0f}{tlm:6.0f}{g10:5.0f} |{mis:5.2f}{nt:4.0f}{fl:6.1f} |{kf:4.0f}{mp:6.0f} |{ln:6.0f}{li3:4.0f}{lmed:5.2f}{ldp:6.1f} |{wt:5.0f}{wr_:6.0f}{rj:5.1f} |{gds:+8.4f}({gsd:.3f}) |{vsw:5.2f}{vark:6.2f} |{vark:6.2f}{wd:6.1f}{g:6.1f}{ae:5.2f} | {ks[0] if ks else float('nan'):.3f}")
