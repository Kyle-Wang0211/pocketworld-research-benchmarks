import sys, json, importlib.util, numpy as np
spec=importlib.util.spec_from_file_location('se','/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/scaleS1/scale_eval.py')
se=importlib.util.module_from_spec(spec); spec.loader.exec_module(se)
est,ref,td,tag,desc,rc,sec=sys.argv[1:8]
r={'tag':tag,'desc':desc,'rc':int(rc),'sec':int(sec)}
import os
BODYONLY = not os.path.exists(est)
try:
    if BODYONLY: r['note']='k from body->cam (runner has no camera output)'
    te,Pe,Qe=se.load_full(est.replace('.cam.tum','.body.tum') if BODYONLY else est)
    r['n_pose']=len(te)
    ext=float(np.linalg.norm(Pe.max(0)-Pe.min(0))) if len(te) else 0
    r['path_m']=float(np.linalg.norm(np.diff(Pe,axis=0),axis=1).sum()) if len(te)>1 else 0
    e=se.evaluate(est.replace('.cam.tum','.body.tum'),ref,cam=True,td=float(td),nseg=4) if BODYONLY else se.evaluate(est,ref,cam=False,td=float(td),nseg=4)
    for k in ['n','k_sim3_fwd','k_sim3_sym','k_pair_med','ate_sim3_cm','ate_se3_cm','k_sim3_fwd_ci95','seg_k']:
        r[k]=e.get(k)
    body=est.replace('.cam.tum','.body.tum')
    eb=se.evaluate(body,ref,cam=False,td=float(td),nseg=0,boot=False)
    r['k_body_raw']=eb['k_sim3_fwd']
    ec=se.evaluate(body,ref,cam=True,td=float(td),nseg=0,boot=False)
    r['k_body2cam']=ec['k_sim3_fwd']
except Exception as ex:
    r['err']=repr(ex)
print(json.dumps(r))
