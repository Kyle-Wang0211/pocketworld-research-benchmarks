#!/usr/bin/python3
"""Tilt of the delivered model's +Y axis vs device gravity (Y-up is assumed by the core's mirror-ghost
delivery filter, official_mirror_ghost.h header, and by Dart viewers). Per registered frame the device gravity
in COLMAP camera axes (core: mandatory_arkit_gravity_v1.cc:74-77) is taken into the model world with the
delivered rotation; tilt = angle(mean direction, -Y)."""
import json, os, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools'); import prep_inputs as P  # noqa
def feed(n):
    p = f'{W}/inputs/feed_{n}.jsonl'
    if not os.path.exists(p): p = f'{W}/base_sfmB/inputs/feed_{n}.jsonl'
    return [json.loads(l) for l in open(p)]
def tilt(run_dir, fn):
    fd = feed(fn); gs = []
    for ln in open(run_dir + '/delivered_poses.txt'):
        a = ln.split()
        if int(a[2]) != 1: continue
        k = int(a[0]); R = P.q2R(*map(float, a[3:7]))
        Ra = P.q2R(*fd[k]['arkitCamFromWorldQwxyz']); g = Ra @ np.array([0, -1., 0]); g = np.array([g[0], -g[1], -g[2]])
        gs.append(R.T @ g)
    m = np.mean(gs, 0); m /= np.linalg.norm(m)
    return float(np.degrees(np.arccos(np.clip(-m[1], -1, 1))))
for rd, fn in [(a.split('=')[0], a.split('=')[1]) for a in sys.argv[1:]]:
    d = rd if rd.startswith('/') else W + '/runs/' + rd
    print('%-28s tilt_vs_device_gravity_deg = %.3f' % (os.path.basename(d), tilt(d, fn)))
