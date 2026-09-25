import sys; sys.path.insert(0,'ana'); from rep import *
import numpy as np
SPX='/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/xr_shared/'
R=REC; slam=R+'_paper_cmp/slam_paper.yaml'
recs={'6e2d':('run-6e2d4b99-896b-4372-ae47-ac0b4679cf18',R+'_euroc_6e2d4b99_640'),
      '5966':('run-5966aec0-cbf1-4abc-af0e-c1fc559da44c',SPX+'euroc640_5966aec0'),
      '4ad6':('run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa',SPX+'euroc640_4ad6e500')}
for key,(rid,base_ds) in recs.items():
    ref=R+rid+'/arkit_poses.tum'; dev=S4+f'/cfg/{key}_640_k0_td8.yaml'
    lines=open(base_ds+'/imu0/data.csv','rb').read().split(b'\r\n'); head=lines[0]; rows=[l for l in lines[1:] if l.strip()]
    D=np.array([[float(x) for x in l.split(b',')] for l in rows])
    for sc in (1.0068, 1.02):
        dd=S4+f'/ds/{key}_as{sc}'
        os.makedirs(dd+'/imu0',exist_ok=True)
        if not os.path.exists(dd+'/cam0'): os.symlink(base_ds+'/cam0', dd+'/cam0')
        with open(dd+'/imu0/data.csv','wb') as f:
            f.write(head+b'\r\n')
            for r in D:
                f.write(f'{int(r[0])},{float(r[1])!r},{float(r[2])!r},{float(r[3])!r},{float(r[4]*sc)!r},{float(r[5]*sc)!r},{float(r[6]*sc)!r}\r\n'.encode())
        run(dd, slam, dev, f'{key}_640_accx{sc}', ref=ref)
