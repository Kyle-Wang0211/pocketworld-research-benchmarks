import sys, os, re, glob, json, numpy as np
sys.path.insert(0,'/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/scaleS1')
from scale_eval import pair_up, sim3, block_bootstrap
R=os.path.expanduser('~/Developer/viobench-recordings/')
RUN={'6e2d':R+'run-6e2d4b99-896b-4372-ae47-ac0b4679cf18','5966':R+'run-5966aec0-cbf1-4abc-af0e-c1fc559da44c','4ad6':R+'run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa'}
def ts(rec): return np.array([int(l.split(',')[0]) for l in list(open(RUN[rec]+'/camera_index.csv'))[1:]])*1e-9
out={}
for p in sorted(glob.glob('runs/*.tum')):
    tag=os.path.basename(p)[:-4]; key=tag.replace('M_','')[:4]
    if key not in RUN: continue
    m=re.search(r'_td([+-]?\d+)',tag); td=(int(m.group(1)) if m else 8)/1000
    t=ts(key)
    try:
        tt,X,Y=pair_up(p, RUN[key]+'/arkit_poses.tum', cam=True, max_dt=0.001, frame_map=(t,np.full(len(t),td)))
        s,_,_,ate=sim3(X,Y); k=1/s
        ci=block_bootstrap(X,Y,tt,lambda a,b:1/sim3(a,b)[0],n_boot=150) if ('base' in tag or 'k0_td8' in tag or tag.endswith('_td+0')) else None
        out[tag]=dict(k=k, n=X.shape[1], sim3_cm=ate*100, ci=ci[:2] if ci else None)
    except Exception as e:
        out[tag]=dict(err=str(e))
json.dump(out,open('runs/rescore_S1.json','w'),indent=1)
for k,v in out.items():
    if 'k' in v: print(f"{k:32s} k_cam={v['k']:.4f} ({(v['k']-1)*100:+6.2f}%) n={v['n']} sim3={v['sim3_cm']:.2f}cm"+(f" CI95 {v['ci'][0]:.4f}-{v['ci'][1]:.4f}" if v.get('ci') else ''))
    else: print(k, v)
