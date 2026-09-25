import sys; sys.path.insert(0,'ana'); from rep import *
which=sys.argv[1]
eps=[-6,-4,-3,-2,-1,-0.5,-0.2,-0.1,0.1,0.2,0.5,1,2,3,4,6]
if which=='phone':
    R=REC; ds=R+'_euroc_6e2d4b99_640'; ref=R+'run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum'
    base=S4+'/cfg/dev640_k0_td8.yaml'; slam=R+'_paper_cmp/slam_paper.yaml'
    fx,fy,cx,cy=1347.7943115234375,1347.7943115234375,957.4692993164062,718.9641723632812
    K=[fx/3,fy/3,(cx+.5)/3-.5,(cy+.5)/3-.5]; pre='6e2d_640'
    pp=[2,5]
else:
    ds='/Users/kaidongwang/Developer/euroc/V1_01_easy_gt/mav0'; ref=S4+'/cfg/v101_gt.tum'
    base=S4+'/cfg/dev_euroc.yaml'; slam=S4+'/cfg/euroc_slam.yaml'; K=[458.654, 457.296, 367.215, 248.375]; pre='v101'
    pp=[2,5]
for e in eps:
    k=[K[0]*(1+e/100),K[1]*(1+e/100),K[2],K[3]]
    d=make_dev(base, S4+f'/cfg/{pre}_f{e:+g}.yaml', intrinsics=k)
    run(ds, slam, d, f'{pre}_f{e:+g}', ref=ref)
for ax in (2,3):
    for dp in pp:
        for sg in (-1,1):
            k=list(K); k[ax]+=sg*dp
            n='cx' if ax==2 else 'cy'
            d=make_dev(base, S4+f'/cfg/{pre}_{n}{sg*dp:+g}.yaml', intrinsics=k)
            run(ds, slam, d, f'{pre}_{n}{sg*dp:+g}', ref=ref)
