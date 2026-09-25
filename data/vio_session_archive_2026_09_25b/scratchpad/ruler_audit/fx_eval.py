# -*- coding: utf-8 -*-
"""焦距 α 对照回放的评分:直接 import 积分 agent 的 preint_eval.run(只把产物目录指到 ruler_audit/fx_runs)。"""
import sys, os, json
sys.dont_write_bytecode=True
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0,SP+'/preint/tools')
import preint_eval as PE
PE.W=SP+'/ruler_audit/fx_runs/'
import eval3; eval3.W=PE.W
AG={'13f5':'1.0133','6d18':'1.0064','7353':'1.0169'}; AA={'13f5':'1.0270','6d18':'1.0154','7353':'1.0247'}
out={}
for sc in ('13f5','6d18','7353'):
    tags=[]
    for cfg in ('scall_am16_swm4','scall_ap0_swm4','scnone_ap0_swp0'):
        for a in ('1',AG[sc],AA[sc]): tags.append('%s_%s_a%s'%(sc,cfg,a))
    for a in ('0.98','0.99','1.01','1.02','1.03','1.04'): tags.append('%s_scall_am16_swm4_s%s'%(sc,a))
    for tag in tags:
        if not os.path.exists(PE.W+tag+'.backend.csv'): continue
        r=PE.run(sc,tag); out[tag]=r['rows']
        for nm in ('front','backend_final'):
            x=r['rows'][nm]
            print('%-30s %-13s k_ARKit %+6.2f%%  ATE %5.2f cm  旋转幅度比 g %.4f  抖动 %.3f°  5s分段 %+5.1f…%+5.1f (sd %.1f)'%(tag,nm,100*(x['k_ark']-1),x['ate_cm'],x['g'],x['jitter_deg'],x['seg5_min'],x['seg5_max'],x['seg5_sd']),flush=True)
json.dump(out,open('fx_eval.json','w'),indent=1,default=float)
