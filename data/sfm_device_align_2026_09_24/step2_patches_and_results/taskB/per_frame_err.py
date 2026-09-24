#!/usr/bin/python3
"""Per-frame centre + rotation error after the core's robust Sim3 (device_align_offline σ=0.040) for selected frames,
plus the depth of the camera's observed scene (median distance device-centre -> ...) not available offline; prints
rotation error and the direction of the centre offset in the camera frame (x right, y down, z forward)."""
import json, os, subprocess, sys
import numpy as np
W = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, W + '/base_sfmB/tools'); import prep_inputs as P  # noqa
pf = sys.argv[1]; sel = [int(v) for v in sys.argv[2].split(',')]
rows = {int(l.split()[0]): [float(v) for v in l.split()[1:]] for l in open(pf) if l.strip()}
r = json.loads(subprocess.run([W + '/build/device_align_offline', pf, '0.04'], capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
s, Rf, tf = r['scale'], P.q2R(*r['q']), np.array(r['t'])
for k in sel:
    Rr, tr = P.q2R(*rows[k][0:4]), np.array(rows[k][4:7]); Rd, td = P.q2R(*rows[k][7:11]), np.array(rows[k][11:14])
    Cr = s * Rf @ (-Rr.T @ tr) + tf; Cd = -Rd.T @ td
    Rr_w = Rr @ Rf.T  # cam_from_deviceworld of recon after Sim3
    dR = Rr_w @ Rd.T; ang = np.degrees(np.arccos(np.clip((np.trace(dR) - 1) / 2, -1, 1)))
    off_cam = Rd @ (Cr - Cd)
    print('frame %3d centre err %6.1f mm  rot err %5.2f deg  offset in device cam frame (x,y,z) mm %s' % (k, 1e3 * np.linalg.norm(Cr - Cd), ang, np.round(1e3 * off_cam, 0)))
