import sys; sys.path.insert(0,'ana'); import rep; from rep import *
rep.RUNNER='/tmp/pw_euroc_ps'
R=REC; slam=R+'_paper_cmp/slam_paper.yaml'; ds=R+'_euroc_6e2d4b99_640'; ref=R+'run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum'
for td in (0,8):
    run(ds, slam, S4+f'/cfg/6e2d_td{td}.yaml' if td==0 else S4+'/cfg/6e2d_640_k0_td8.yaml', f'M_6e2d_640_td{td:+d}', ref=ref)
