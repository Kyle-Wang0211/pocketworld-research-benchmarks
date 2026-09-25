#!/usr/bin/env python3
"""one line per run: global k/ATE, fixed-segment Sim3 k (dip 8-15 s, high 22.5-26.5 s), max excess step (jump),
and (if a log exists) mean loc inlier fraction + rejected tracks in the two segments."""
import sys,json,os,numpy as np,importlib.util
spec=importlib.util.spec_from_file_location('tj','/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/dip13f/tools/traj.py'); tj=importlib.util.module_from_spec(spec); spec.loader.exec_module(tj); se=tj.se
T0=254666.645033333
SEG={'dip':(8.0,15.0),'hi':(22.5,26.5),'q1':(1.5,8.0),'late':(26.5,30.0)}
def one(cam):
    t,X,Y=tj.load_pair(cam); e=se.estimators(X,Y,t)
    r={'k':e['k_sim3_fwd'],'ate':e['ate_sim3_cm'],'n':e['n']}
    for k,(a,b) in SEG.items():
        m=(t-T0>=a)&(t-T0<b); r['k_'+k]=1/se.sim3(X[:,m],Y[:,m])[0] if m.sum()>20 else np.nan
    s,R,tt,_=se.sim3(X,Y); Xa=s*R@X+tt
    de=np.linalg.norm(np.diff(Xa,axis=1),axis=0); dr=np.linalg.norm(np.diff(Y,axis=1),axis=0); tm=t[1:]-T0
    ex=de-dr
    r['jump']=float(ex[(tm>25.0)&(tm<27.5)].max()*100)
    r['jump_all']=float(np.sort(ex[tm>3])[-3:].mean()*100)  # mean of 3 largest excess steps after 3 s
    r['n_jump2']=int((ex[tm>3]>0.02).sum())
    log=cam.replace('.cam.tum','.jsonl')
    if os.path.exists(log):
        L=[];Wn=[]
        for l in open(log):
            if '"ev":"loc"' in l or '"ev":"win"' in l:
                d=json.loads(l); (L if d['ev']=='loc' else Wn).append(d)
        for k,(a,b) in SEG.items():
            ll=[d for d in L if a<=d['t']-T0<b]; ww=[d for d in Wn if a<=d['t']-T0<b]
            r['in3_'+k]=np.mean([d['in3']/max(d['n'],1) for d in ll]) if ll else np.nan
            r['map_'+k]=np.mean([d['n'] for d in ll]) if ll else np.nan
            r['rej_'+k]=np.mean([d['rej_rpe'] for d in ww]) if ww else np.nan
    return r
if __name__=='__main__':
    print(f"{'run':24s}  k      ATEcm  k_q1   k_dip  k_hi   k_late  jump  jmp3  n>2cm | in3 dip/hi  map dip/hi  rej dip/hi")
    for c in sys.argv[1:]:
        try: r=one(c)
        except Exception as ex: print(c,'ERR',ex); continue
        s=f"{os.path.basename(c).replace('.cam.tum',''):24s} {r['k']:.4f} {r['ate']:5.2f}  {r['k_q1']:.3f}  {r['k_dip']:.3f}  {r['k_hi']:.3f}  {r['k_late']:.3f}  {r['jump']:4.1f}  {r['jump_all']:4.1f}  {r['n_jump2']:3d}"
        if 'in3_dip' in r: s+=f" | {r['in3_dip']:.2f}/{r['in3_hi']:.2f}  {r['map_dip']:4.0f}/{r['map_hi']:3.0f}  {r['rej_dip']:4.1f}/{r['rej_hi']:4.1f}"
        print(s)
