#!/usr/bin/env python3
"""scene-generic canonical scoring (scaleS1 scale_eval: camera rows, Umeyama Sim3 est->ARKit, quarters),
td auto-detected from the pose-time offset. Usage: summ_any.py <scene> run.cam.tum ..."""
import sys,os,numpy as np,importlib.util
spec=importlib.util.spec_from_file_location('tj','/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/dip13f/tools/traj.py'); tj=importlib.util.module_from_spec(spec); spec.loader.exec_module(tj); se=tj.se
R=os.path.expanduser('~/Developer/viobench-recordings/')
REF={'13f5':R+'run-13f53d2f-5935-4b1a-a499-4dc8367ea935/arkit_poses.tum','fb5d':R+'run-fb5d3a8f-6e31-463e-989d-bd73bb3a2def/ruler_subset/arkit_poses.tum',
     '6e2d':R+'run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum','5966':R+'run-5966aec0-cbf1-4abc-af0e-c1fc559da44c/arkit_poses.tum','4ad6':R+'run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa/arkit_poses.tum'}
sc=sys.argv[1]; ref=REF[sc]
print(f"{'run':22s} td_ms   n    k      ATEcm  quarters                       worst-q  jumps>2cm")
for c in sys.argv[2:]:
    try:
        td=tj.detect_td(c,ref); t,X,Y=se.pair_up(c,ref,cam=False,td=td); e=se.estimators(X,Y,t); q=se.segments(X,Y,t,4)
        s,Rm,tt,_=se.sim3(X,Y); Xa=s*Rm@X+tt; ex=np.linalg.norm(np.diff(Xa,axis=1),axis=0)-np.linalg.norm(np.diff(Y,axis=1),axis=0)
        nj=int((ex[(t[1:]-t[0])>2]>0.02).sum()); wq=max(q,key=lambda x:abs(x-1))
        print(f"{os.path.basename(c).replace('.cam.tum',''):22s} {td*1000:+5.2f} {e['n']:4d} {e['k_sim3_fwd']:.4f} {e['ate_sim3_cm']:5.2f}  "+' '.join(f'{x:.3f}' for x in q)+f"   {wq:.3f}   {nj}")
    except Exception as ex: print(c,'ERR',ex)
