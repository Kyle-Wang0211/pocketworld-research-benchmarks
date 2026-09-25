import sys; sys.path.insert(0,'ana'); from rep import *
R=REC; ds=R+'_euroc_6e2d4b99_640'; ref=R+'run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum'
fx,fy,cx,cy=1347.7943115234375,1347.7943115234375,957.4692993164062,718.9641723632812
K0=[fx/3,fy/3,(cx+.5)/3-.5,(cy+.5)/3-.5]
dev=make_dev(R+'_paper_cmp/dev_paper640_td8.yaml', S4+'/cfg/dev640_k0_td8.yaml', intrinsics=K0)
run(ds, R+'_paper_cmp/slam_paper.yaml', dev, '6e2d_640_paper_k0_td8', ref=ref)
run(ds, R+'_sweep/slam_bench.yaml', dev, '6e2d_640_bench_k0_td8', ref=ref)
run(ds, R+'_paper_cmp/slam_paper.yaml', R+'_paper_cmp/dev_paper640_td8.yaml', '6e2d_640_paper_kup_td8', ref=ref)
