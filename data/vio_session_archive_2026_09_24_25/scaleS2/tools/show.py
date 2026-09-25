import json,sys
f='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/scaleS2/runs/results.jsonl'
pat=sys.argv[1] if len(sys.argv)>1 else ''
for l in open(f):
    r=json.loads(l)
    if pat not in r['tag']: continue
    k=r.get('k_sim3_fwd'); 
    if k is None: print('%-44s ERR %s rc=%s'%(r['tag'],r.get('err'),r['rc'])); continue
    ci=r.get('k_sim3_fwd_ci95') or [0,0]
    seg=' '.join('%+.1f'%((x-1)*100) for x in (r.get('seg_k') or []) if x)
    print('%-44s scale(cam) %+6.2f%% [%+.1f,%+.1f] body %+6.2f%% | Sim3 %5.2f SE3 %6.2f cm | n %4d path %6.2f m | seg %s'%(r['tag'],(k-1)*100,(ci[0]-1)*100,(ci[1]-1)*100,((r.get('k_body_raw') or 1)-1)*100,r['ate_sim3_cm'],r['ate_se3_cm'],r['n'],r['path_m'],seg))
