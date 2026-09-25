#!/usr/bin/env python3
"""Rebuild the ZJU sequence folder in the benchmark's own layout (camera/imu/groundtruth sensor.yaml + data.csv)
from the files kept on disk, and convert XRSLAM body poses to camera poses (T_wc = T_wb T_bc) for eval-vislam."""
import os, sys
import numpy as np
from scipy.spatial.transform import Rotation as Rot
W = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata"
seq = sys.argv[1]
D = f"{W}/ds/zju/{seq}"; E = f"{W}/work/evs/{seq}"
for s in ("camera", "imu", "groundtruth"):
    os.makedirs(f"{E}/{s}", exist_ok=True)
    open(f"{E}/{s}/sensor.yaml", "w").write(open(f"{D}/{s}_sensor.yaml").read())
with open(f"{E}/camera/data.csv", "w") as f:
    f.write("#t[s:double],filename[string]\n")
    for ln in open(f"{D}/mav0/cam0/data.csv"):
        if ln[0].isdigit():
            t, fn = ln.strip().split(',')
            f.write(f"{int(t)*1e-9:.9f},{fn}\n")
with open(f"{E}/imu/data.csv", "w") as f:
    f.write("#t[s:double],w.x[rad/s:double],w.y[rad/s:double],w.z[rad/s:double],a.x[m/s^2:double],a.y[m/s^2:double],a.z[m/s^2:double]\n")
    for ln in open(f"{D}/mav0/imu0/data.csv"):
        if ln[0].isdigit():
            v = ln.strip().split(',')
            f.write(f"{int(v[0])*1e-9:.9f}," + ",".join(v[1:7]) + "\n")
with open(f"{E}/groundtruth/data.csv", "w") as f:
    f.write("#t[s:double],q.x[double],q.y[double],q.z[double],q.w[double],p.x[m:double],p.y[m:double],p.z[m:double]\n")
    for ln in open(f"{D}/gt.tum"):
        t, x, y, z, qx, qy, qz, qw = ln.split()
        f.write(f"{t},{qx},{qy},{qz},{qw},{x},{y},{z}\n")
# camera extrinsic from the dataset's camera sensor.yaml
cam = {}
for ln in open(f"{D}/camera_sensor.yaml"):
    ln = ln.split('#')[0]
    if ':' in ln:
        k, v = ln.split(':', 1); cam[k.strip()] = v.strip()
q_bc = [float(x) for x in cam['q'].strip('[]').split(',')]; p_bc = np.array([float(x) for x in cam['p'].strip('[]').split(',')])
R_bc = Rot.from_quat(q_bc)
for L in sys.argv[2:]:
    A = np.loadtxt(f"{W}/runs/zju/{seq}.{L}.tum")
    A = A[A[:, 0] > 1e-6]
    R_wb = Rot.from_quat(A[:, 4:8]); p_c = A[:, 1:4] + R_wb.apply(p_bc); q_c = (R_wb * R_bc).as_quat()
    np.savetxt(f"{E}/{seq}.{L}.cam.tum", np.c_[A[:, 0], p_c, q_c], fmt="%.9f")
print("ok", E)
