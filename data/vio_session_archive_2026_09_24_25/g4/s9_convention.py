import sys, csv, numpy as np
from g4lib import *
for key in RUNS:
    run_sub = RUNS[key]['sub']
    rows = LR._tum_rows(os.path.join(run_sub, 'arkit_poses.tum'))
    ts = [t for t, _, _ in rows]
    P, _ = LR.arkit_poses(run_sub, os.path.join(run_sub, 'arkit_poses.tum'), ts)
    out = os.path.join(WS, f'ark_as_xr_{key}.csv')
    with open(out, 'w') as f:
        f.write('recording_frame,t_ns,tx,ty,tz,qx,qy,qz,qw,engine_t\n')
        for i, t in enumerate(sorted(P)):
            R, C = P[t]; q = rmat_to_quat(R)
            # 回代核对
            assert np.abs(LR.quat_to_rmat(*q) - R).max() < 1e-9
            f.write('%d,%d,%.9f,%.9f,%.9f,%.12f,%.12f,%.12f,%.12f,%.9f\n' % (i, t, *C, *q, t * 1e-9))
    print(key, out, len(P))
