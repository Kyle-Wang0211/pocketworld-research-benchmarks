import sys; sys.path.insert(0,'ana'); from rep import *
import numpy as np
SPX='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/xr_shared/'
R=REC; slam=R+'_paper_cmp/slam_paper.yaml'; tmpl=S4+'/cfg/dev640_k0_td8.yaml'
recs={'6e2d':('run-6e2d4b99-896b-4372-ae47-ac0b4679cf18',R+'_euroc_6e2d4b99_640',[1347.7943115234375,957.4692993164062,718.9641723632812]),
      '5966':('run-5966aec0-cbf1-4abc-af0e-c1fc559da44c',SPX+'euroc640_5966aec0',[1280.6334228515625,957.7257080078125,718.9722900390625]),
      '4ad6':('run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa',SPX+'euroc640_4ad6e500',[1279.01953125,957.751708984375,719.0894775390625])}
qd=np.load('ana/qbc_data.npy',allow_pickle=True).item()
def canon(q): q=np.array(q); return q if q[0]<0 else -q
qs={k[4:8]:canon(v) for k,v in qd.items()}
qmean=np.mean([v for v in qs.values()],0); qmean/=np.linalg.norm(qmean)
what=sys.argv[1]
for key,(rid,ds,(f,cx,cy)) in recs.items():
    ref=R+rid+'/arkit_poses.tum'
    K=[f/3,f/3,(cx+.5)/3-.5,(cy+.5)/3-.5]
    base=make_dev(tmpl, S4+f'/cfg/{key}_640_k0_td8.yaml', intrinsics=K)
    if what=='rbc':
        run(ds, slam, base, f'{key}_640_base', ref=ref) if key!='6e2d' else None
        d=make_dev(base, S4+f'/cfg/{key}_qbc_own.yaml', q_bc=list(qs[key])); run(ds, slam, d, f'{key}_640_qbc_own', ref=ref)
        d=make_dev(base, S4+f'/cfg/{key}_qbc_mean.yaml', q_bc=list(qmean)); run(ds, slam, d, f'{key}_640_qbc_mean', ref=ref)
    elif what=='fx' and key!='6e2d':
        for e in (-3,-1,1,3):
            d=make_dev(base, S4+f'/cfg/{key}_f{e:+d}.yaml', intrinsics=[K[0]*(1+e/100),K[1]*(1+e/100),K[2],K[3]]); run(ds, slam, d, f'{key}_640_f{e:+d}', ref=ref)
print('qmean', np.round(qmean,7))
