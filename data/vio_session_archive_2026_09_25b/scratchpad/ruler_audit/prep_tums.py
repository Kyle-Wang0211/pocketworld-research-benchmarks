# -*- coding: utf-8 -*-
"""给 LiDAR 米尺 v2 准备 XRSLAM 相机位姿 TUM(--camera),帧 = 全部深度帧(不只 99 帧子集)。
逐项照抄积分 agent 的 preint/tools/make_ruler_tums.py(只 import 其函数,不改原文件):
  front = keyed.csv 原值(深度帧都是引擎收的帧 ⇒ 不插值);final = backend.csv kind 2/3 → make_tums.interp_backend
  (陀螺积分 + 端点残差线性分摊 + Hermite)到深度帧的引擎时间。外参取回放用的 preint/cfg/dev_<sc>.yaml。
回放产物取 ruler_audit/fx_runs/<sc>_<cfg>_a1.*(与 preint/runs 同名产物逐位相同,已核)。"""
import csv, json, re, sys
sys.dont_write_bytecode=True
import numpy as np
SP='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad'
sys.path.insert(0,SP+'/preint/tools'); sys.path.insert(0,SP+'/wobble/tools')
import wob
from calib_joint_q import r2q
from gyrofit import GyroInt
from make_tums import interp_backend, fmt_t
RA=SP+'/ruler_audit/'; W=RA+'fx_runs/'
def ext(sc):
    txt=open(SP+'/preint/cfg/dev_%s.yaml'%sc).read()
    q=[float(x) for x in re.search(r'q_bc:\s*\[([^\]]+)\]',txt).group(1).split(',')]
    p=np.array([float(x) for x in re.search(r'p_bc:\s*\[([^\]]+)\]',txt).group(1).split(',')])
    return wob.qmat(np.array([q]))[0],p
for sc in ('13f5','6d18','7353'):
    Rbc,pbc=ext(sc); G=GyroInt(sc)
    dts=[json.loads(l)['t_ns'] for l in open(RA+'full_%s/depth.pwvi'%sc) if l.strip()]
    for cfg in ('scall_am16_swm4','scall_ap0_swm4','scnone_ap0_swp0'):
        tag='%s_%s_a1'%(sc,cfg)
        eng={int(l.split()[1]):float(l.split()[0]) for l in open(W+tag+'.map')}
        st,win={},{}
        for r in csv.DictReader(open(W+tag+'.backend.csv')):
            if int(r['t_ns'])<0 or r['kind'] not in ('2','3'): continue
            t=float(r['engine_t'])
            R=wob.qmat(np.array([[float(r['body_q'+c]) for c in 'xyzw']]))[0]
            p=np.array([float(r['body_t'+c]) for c in 'xyz']); v=np.array([float(r['v'+c]) for c in 'xyz'])
            bg=np.array([float(r['bg'+c]) for c in 'xyz'])
            (st if r['kind']=='2' else win)[t]=(t,R,p,v,bg)
        for t,x in win.items(): st.setdefault(t,x)
        states=sorted(st.values(),key=lambda x:x[0])
        front={int(r['t_ns']):r for r in csv.DictReader(open(W+tag+'.keyed.csv'))}
        rf,rb=[],[]
        for tn in dts:
            if tn in front:
                r=front[tn]; rf.append('%s %s %s %s %s %s %s %s'%(fmt_t(tn),r['tx'],r['ty'],r['tz'],r['qx'],r['qy'],r['qz'],r['qw']))
            if tn in eng:
                x=interp_backend(G,states,eng[tn],Rbc,pbc)
                if x is not None:
                    R,p=x; rb.append('%s %.7f %.7f %.7f %.7f %.7f %.7f %.7f'%(fmt_t(tn),*p,*r2q(R)))
        open(RA+'tums/%s_%s_front.tum'%(sc,cfg),'w').write('\n'.join(rf)+'\n')
        open(RA+'tums/%s_%s_final.tum'%(sc,cfg),'w').write('\n'.join(rb)+'\n')
        print(sc,cfg,'深度帧 %d:前端 %d 行,后端定稿 %d 行'%(len(dts),len(rf),len(rb)),flush=True)
