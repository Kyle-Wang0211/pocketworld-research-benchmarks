#!/usr/bin/python3
"""For a fix run, write pre_<run>/ = the SAME run's model with the applied DEVICE-ALIGN-V1 Sim3 inverted
(read from its device_alignment_v1 jsonl record): delivered_poses.txt (centres C_pre = T^-1 C, R_pre = R Rt)
and cloud.ply (float32, like the core). Everything else is symlinked, so B's analyze_takeover can score
post vs pre of one and the same run (removes run-to-run nondeterminism from the geometry check)."""
import json, os, sys, re
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools'); import prep_inputs as P  # noqa
for run in sys.argv[1:]:
    d = f'{W}/runs/{run}'; o = f'{W}/runs/pre_{run}'; os.makedirs(o, exist_ok=True)
    ja = [json.loads(l) for l in open(d + '/sfm_match_fail.jsonl', errors='replace') if '"device_alignment_v1"' in l][0]
    s = ja['scale']; Rt = P.q2R(ja['qw'], ja['qx'], ja['qy'], ja['qz']); tt = np.array([ja['tx'], ja['ty'], ja['tz']])
    inv = lambda X: (Rt.T @ (X - tt).T).T / s
    with open(o + '/delivered_poses.txt', 'w') as f:
        for ln in open(d + '/delivered_poses.txt'):
            a = ln.split()
            if int(a[2]) != 1: f.write(ln); continue
            R = P.q2R(*map(float, a[3:7])); t = np.array(list(map(float, a[7:10]))); C = -R.T @ t
            Cp = inv(C[None])[0]; Rp = R @ Rt; tp = -Rp @ Cp; q = P.R2q(Rp)
            f.write('%s %s %s %s %s\n' % (a[0], a[1], a[2], ' '.join('%.17g' % v for v in q), ' '.join('%.17g' % v for v in tp)))
    b = open(d + '/cloud.ply', 'rb').read(); h = b.index(b'end_header\n') + 11
    n = int(re.search(rb'element vertex (\d+)', b[:h]).group(1))
    dt = np.dtype([('x', '<f4'), ('y', '<f4'), ('z', '<f4'), ('r', 'u1'), ('g', 'u1'), ('b', 'u1')])
    a = np.frombuffer(b[h:h + n * 15], dtype=dt).copy()
    X = np.stack([a['x'], a['y'], a['z']], 1).astype(np.float64); Xp = inv(X)
    a['x'], a['y'], a['z'] = Xp[:, 0], Xp[:, 1], Xp[:, 2]
    open(o + '/cloud.ply', 'wb').write(b[:h] + a.tobytes())
    for f in ('run.log', 'per_frame.jsonl', 'sfm_match_fail.jsonl'):
        if not os.path.exists(o + '/' + f): os.symlink(d + '/' + f, o + '/' + f)
    print(run, 'inverted scale', s)
