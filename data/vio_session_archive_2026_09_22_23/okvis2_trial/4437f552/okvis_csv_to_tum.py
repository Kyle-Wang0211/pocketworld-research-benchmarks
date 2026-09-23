#!/usr/bin/env python3
"""OKVIS2 trajectory csv (T_WS, IMU/body pose) -> TUM.

usage: okvis_csv_to_tum.py <in.csv> <out_body.tum> <out_cam.tum>

CSV columns (okvis2 TrajectoryOutput::createCsvFile / writeStateToCsv):
  timestamp[ns], p_WS_W_{x,y,z}, q_WS_{x,y,z,w}, v..., b_g..., b_a...

T_SC is the same camera->IMU transform fed to OKVIS in the yaml
(XRSLAM q_bc/p_bc, iPhone 14 Pro).  T_WC = T_WS * T_SC.
"""
import sys
import numpy as np

R_SC = np.array([[0.0, -1.0, 0.0],
                 [-1.0, 0.0, 0.0],
                 [0.0, 0.0, -1.0]])
p_SC = np.array([0.03290364, -0.00696553, -0.00286231])


def quat_to_R(qx, qy, qz, qw):
    n = np.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    qx, qy, qz, qw = qx / n, qy / n, qz / n, qw / n
    return np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw), 2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz), 2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw), 1 - 2 * (qx * qx + qy * qy)]])


def R_to_quat(R):
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        qw = 0.25 * s
        qx = (R[2, 1] - R[1, 2]) / s
        qy = (R[0, 2] - R[2, 0]) / s
        qz = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
        qw = (R[2, 1] - R[1, 2]) / s
        qx = 0.25 * s
        qy = (R[0, 1] + R[1, 0]) / s
        qz = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
        qw = (R[0, 2] - R[2, 0]) / s
        qx = (R[0, 1] + R[1, 0]) / s
        qy = 0.25 * s
        qz = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
        qw = (R[1, 0] - R[0, 1]) / s
        qx = (R[0, 2] + R[2, 0]) / s
        qy = (R[1, 2] + R[2, 1]) / s
        qz = 0.25 * s
    return qx, qy, qz, qw


def main():
    src, out_body, out_cam = sys.argv[1], sys.argv[2], sys.argv[3]
    nb = nc = 0
    with open(src) as f, open(out_body, 'w') as fb, open(out_cam, 'w') as fc:
        first = f.readline()  # header
        assert 'timestamp' in first, first
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            fld = [s.strip() for s in ln.split(',')]
            if len(fld) < 8:
                continue
            t = int(fld[0]) * 1e-9
            p = np.array([float(fld[1]), float(fld[2]), float(fld[3])])
            qx, qy, qz, qw = (float(fld[4]), float(fld[5]), float(fld[6]), float(fld[7]))
            fb.write('%.9f %.9f %.9f %.9f %.9f %.9f %.9f %.9f\n'
                     % (t, p[0], p[1], p[2], qx, qy, qz, qw))
            nb += 1
            R_WS = quat_to_R(qx, qy, qz, qw)
            p_WC = p + R_WS @ p_SC
            cqx, cqy, cqz, cqw = R_to_quat(R_WS @ R_SC)
            fc.write('%.9f %.9f %.9f %.9f %.9f %.9f %.9f %.9f\n'
                     % (t, p_WC[0], p_WC[1], p_WC[2], cqx, cqy, cqz, cqw))
            nc += 1
    print('wrote %d body / %d cam poses' % (nb, nc))


if __name__ == '__main__':
    main()
