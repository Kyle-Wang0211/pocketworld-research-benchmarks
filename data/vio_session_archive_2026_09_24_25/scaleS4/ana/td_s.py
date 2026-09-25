import sys; sys.path.insert(0,'ana'); from rep import *
SPX='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/xr_shared/'
R=REC; slam=R+'_paper_cmp/slam_paper.yaml'
recs={'6e2d':('run-6e2d4b99-896b-4372-ae47-ac0b4679cf18',R+'_euroc_6e2d4b99_640',(0,4,6,10,12)),
      '5966':('run-5966aec0-cbf1-4abc-af0e-c1fc559da44c',SPX+'euroc640_5966aec0',(0,4,12)),
      '4ad6':('run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa',SPX+'euroc640_4ad6e500',(0,4,12))}
for key,(rid,ds,tds) in recs.items():
    base=S4+f'/cfg/{key}_640_k0_td8.yaml'; ref=R+rid+'/arkit_poses.tum'
    for td in tds:
        d=make_dev(base, S4+f'/cfg/{key}_td{td}.yaml', time_offset=td/1000)
        run(ds, slam, d, f'{key}_640_td{td:+d}', ref=ref)
