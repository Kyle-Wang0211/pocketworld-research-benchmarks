#!/usr/bin/env python3
"""ADVIO sequence -> EuRoC-layout CSVs + GT/ARKit TUM + device yaml, fetching ONLY the needed zip members
(iphone/*.csv, iphone/frames.mov, ground-truth/*) from the official Zenodo record via HTTP Range
(zip CRC32 verified by zipfile; sha256 of every member recorded).  frames.mov is kept only as a temp
file for the replay and deleted by advio_run.sh afterwards.

Conventions (ADVIO README + calibration/README):
  * iPhone accelerometer: the README says "g", but the stored values are m/s^2 (median |a| 9.75) and
    already SPECIFIC FORCE (+up): rotated by the ARKit orientation the mean is [0.03, 9.75, -0.01] in
    ARKit's y-up world (tilt 0.2 deg) => used as is (a_imu = acc).  (GT orientation is ~20 deg off from
    that; only GT *positions* are used for scale.)
  * gyro: rad/s, device frame, unchanged.  Gyro and accel are separate 100 Hz streams -> accel is
    linearly interpolated onto gyro stamps (EuRoC imu0 rows need both).
  * camera: 720x1280 portrait, 60 fps H.264; downscaled 2x (ffmpeg area = 2x2 box, like the M runner's
    --downscale 2) to 360x640; K' = K/2 with c' = c/2 - 0.25; radtan coefficients unchanged.
  * T_cam_imu (Kalibr) from calibration/iphone-0X.yaml; XRSLAM wants camera-in-body: T_bc = inv(T_cam_imu).
usage: advio_prep.py NN
"""
import hashlib
import json
import os
import sys
import time
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from httpzip import HttpFile  # noqa: E402

W = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata"
G0 = 9.80665
# calibration/README.md table (fx fy cx cy r1 r2 k1 k2 -> radtan k1 k2 p1 p2 in the yaml's order)
CAL = {
    range(1, 13): ("iphone-02", [1077.2, 1079.3, 362.145, 636.3873], [0.0478, 0.0339, -0.00033, -0.00091]),
    range(13, 18): ("iphone-03", [1082.4, 1084.4, 364.6778, 643.3080], [0.0366, 0.0803, 0.000783, -0.000215]),
    range(18, 20): ("iphone-01", [1076.9, 1078.5, 360.96, 619.31], [0.0510, -0.0354, -0.0054, 0.0473]),
    range(20, 24): ("iphone-04", [1081.1, 1082.1, 359.59, 640.79], [0.0556, -0.0454, 0.0009, -0.0018]),
}
T_CAM_IMU = np.array([[0.9999763379093255, -0.004079205042965442, -0.005539287650170447, -0.008977668364731128],
                      [-0.004066386342107199, -0.9999890330121858, 0.0023234365646622014, 0.07557012320238939],
                      [-0.00554870467502187, -0.0023008567036498766, -0.9999819588046867, -0.005545773942541918],
                      [0.0, 0.0, 0.0, 1.0]])


def rot2q(R):
    tr = np.trace(R)
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2; w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s; y = (R[0, 2] - R[2, 0]) / s; z = (R[1, 0] - R[0, 1]) / s
    else:
        i = np.argmax(np.diag(R))
        if i == 0:
            s = np.sqrt(1 + R[0, 0] - R[1, 1] - R[2, 2]) * 2
            w = (R[2, 1] - R[1, 2]) / s; x = 0.25 * s; y = (R[0, 1] + R[1, 0]) / s; z = (R[0, 2] + R[2, 0]) / s
        elif i == 1:
            s = np.sqrt(1 + R[1, 1] - R[0, 0] - R[2, 2]) * 2
            w = (R[0, 2] - R[2, 0]) / s; x = (R[0, 1] + R[1, 0]) / s; y = 0.25 * s; z = (R[1, 2] + R[2, 1]) / s
        else:
            s = np.sqrt(1 + R[2, 2] - R[0, 0] - R[1, 1]) * 2
            w = (R[1, 0] - R[0, 1]) / s; x = (R[0, 2] + R[2, 0]) / s; y = (R[1, 2] + R[2, 1]) / s; z = 0.25 * s
    q = np.array([x, y, z, w]); return q / np.linalg.norm(q)


def csv_rows(txt):
    out = []
    for ln in txt.splitlines():
        ln = ln.strip()
        if not ln or ln[0].isalpha() or ln.startswith('#'):
            continue
        out.append([float(x) for x in ln.split(',')])
    return np.array(out)


def main():
    n = int(sys.argv[1]); NN = f"{n:02d}"
    D = f"{W}/ds/advio/{NN}"; os.makedirs(D + "/mav0/cam0", exist_ok=True); os.makedirs(D + "/mav0/imu0", exist_ok=True)
    st = os.statvfs(os.path.expanduser("~")); fg = st.f_bavail * st.f_frsize / 2 ** 30
    print(f"[advio-{NN}] free {fg:.2f} GiB", flush=True)
    if fg < 2.2:
        print("STOP: free < 2 GiB (+0.2 margin for the temp mov)"); sys.exit(2)
    url = f"https://zenodo.org/api/records/1476931/files/advio-{NN}.zip/content"
    if os.path.exists(D + "/frames.mov") and os.path.exists(D + "/iphone_arkit.csv"):
        mem = {"iphone/frames.mov": b""}
        for k in ["iphone/frames.csv", "iphone/accelerometer.csv", "iphone/gyro.csv", "ground-truth/pose.csv",
                  "iphone/arkit.csv"]:
            mem[k] = open(D + "/" + k.replace('/', '_'), "rb").read()
        return convert(n, NN, D, mem)
    f = HttpFile(url, block=1 << 20)
    z = zipfile.ZipFile(f)
    want = [i for i in z.infolist() if not i.is_dir() and (f"/iphone/" in i.filename or "/ground-truth/" in i.filename)
            and not i.filename.endswith(("magnetometer.csv", "barometer.csv", "platform-locations.csv"))]
    mem = {}
    man = []
    for i in want:
        b = z.read(i.filename)  # zipfile verifies CRC32
        mem[i.filename.split('/', 1)[1]] = b
        man.append(dict(member=i.filename, bytes=len(b), sha256=hashlib.sha256(b).hexdigest(), crc32=f"{i.CRC:08x}"))
    rec = dict(dataset="ADVIO", seq=f"advio-{NN}", url=url, zip_bytes=f.size, bytes_fetched=f.fetched,
               members=man, stored_on_disk="csv + temp frames.mov (deleted after replay)",
               date=time.strftime("%Y-%m-%d %H:%M:%S"))
    with open(f"{W}/ds/manifest.jsonl", "a") as fh:
        fh.write(json.dumps(rec) + "\n")
    print(f"[advio-{NN}] fetched {f.fetched/1e6:.1f} MB of {f.size/1e6:.1f} MB zip", flush=True)
    open(D + "/frames.mov", "wb").write(mem["iphone/frames.mov"])
    for k in mem:
        if k.endswith(".csv"):
            open(D + "/" + k.replace('/', '_'), "wb").write(mem[k])
    return convert(n, NN, D, mem)


def convert(n, NN, D, mem):

    fr = csv_rows(mem["iphone/frames.csv"].decode())
    acc = csv_rows(mem["iphone/accelerometer.csv"].decode())
    gyr = csv_rows(mem["iphone/gyro.csv"].decode())
    gt = csv_rows(mem["ground-truth/pose.csv"].decode())
    ark = csv_rows(mem["iphone/arkit.csv"].decode())
    print(f"frames {fr.shape} acc {acc.shape} gyro {gyr.shape} gt {gt.shape} arkit {ark.shape}")
    print("frames[0:3]", fr[:3].tolist()); print("gt[0]", gt[0].tolist()); print("arkit[0]", ark[0].tolist())
    print("acc[0]", acc[0].tolist(), "gyr[0]", gyr[0].tolist())
    # cam0/data.csv: one row per video frame, in video order.
    # TIME BASE: the official ADVIO tooling (scripts/rosbag/sync-data.py: `t=t-t[0]` on arkit.csv, whose rows
    # are the frame triggers) shifts frame/ARKit stamps so the first frame is at 0.  Verified independently:
    # image shift (phase correlation) vs gyro correlates 0.98 at gyro_t = frame_t - 0.295 s on advio-09,
    # frames[0] = 0.2936 s.  Without the shift XRSLAM diverges to km within seconds.
    t0f = fr[0, 0]
    with open(D + "/mav0/cam0/data.csv", "w", newline="\r\n") as fh:
        fh.write("#timestamp [ns],filename\n")
        for k, row in enumerate(fr):
            fh.write(f"{int(round((row[0] - t0f) * 1e9))},{k:06d}.png\n")
    ark = ark.copy(); ark[:, 0] -= t0f
    # imu0: gyro stamps, accel interpolated, sign/unit converted
    tg = gyr[:, 0]; m = (tg >= acc[0, 0]) & (tg <= acc[-1, 0])
    A = np.stack([np.interp(tg[m], acc[:, 0], acc[:, j]) for j in (1, 2, 3)], 1) * 1.0
    with open(D + "/mav0/imu0/data.csv", "w", newline="\r\n") as fh:
        fh.write("#timestamp [ns],w_x,w_y,w_z,a_x,a_y,a_z\n")
        for t, w, a in zip(tg[m], gyr[m, 1:4], A):
            fh.write(f"{int(round(t * 1e9))},{w[0]:.9f},{w[1]:.9f},{w[2]:.9f},{a[0]:.9f},{a[1]:.9f},{a[2]:.9f}\n")
    # GT & ARKit -> TUM.  ADVIO pose rows: t, x, y, z, qw, qx, qy, qz  (ADVIO show_dataset.py / my_utils.py)
    for src, name in ((gt, "gt.tum"), (ark, "arkit.tum")):
        with open(D + "/" + name, "w") as fh:
            for r in src:
                fh.write(f"{r[0]:.9f} {r[1]:.6f} {r[2]:.6f} {r[3]:.6f} {r[5]:.9f} {r[6]:.9f} {r[7]:.9f} {r[4]:.9f}\n")
    # device yaml
    cal = next(v for k, v in CAL.items() if n in k)
    K = cal[1]; dist = cal[2]
    Kp = [K[0] / 2, K[1] / 2, K[2] / 2 - 0.25, K[3] / 2 - 0.25]
    T_bc = np.linalg.inv(T_CAM_IMU); q_bc = rot2q(T_bc[:3, :3]); p_bc = T_bc[:3, 3]
    tmpl_path = f"{W}/xrslam-wt-O/configs/iphonex.yaml"
    head = open(tmpl_path).read().split('cam0:')[0]
    R = T_bc
    cam0 = f"""cam0:
  # [gtdata] ADVIO {cal[0]} (calibration/README.md), image 2x downscaled 720x1280 -> 360x640
  T_BS:
    cols: 4
    rows: 4
    data: [{R[0,0]:.12f}, {R[0,1]:.12f}, {R[0,2]:.12f}, {R[0,3]:.12f},
           {R[1,0]:.12f}, {R[1,1]:.12f}, {R[1,2]:.12f}, {R[1,3]:.12f},
           {R[2,0]:.12f}, {R[2,1]:.12f}, {R[2,2]:.12f}, {R[2,3]:.12f},
           0.0, 0.0, 0.0, 1.0]
  resolution: [360, 640]
  camera_model: pinhole
  distortion_model: radtan
  intrinsics: [{Kp[0]}, {Kp[1]}, {Kp[2]}, {Kp[3]}] # fu, fv, cu, cv
  camera_distortion_flag: 1
  distortion: [{dist[0]}, {dist[1]}, {dist[2]}, {dist[3]}] # k1, k2, p1, p2
  camera_readout_time: 0.0
  time_offset: 0.0
  extrinsic:
    q_bc: [{q_bc[0]:.12f}, {q_bc[1]:.12f}, {q_bc[2]:.12f}, {q_bc[3]:.12f}] # x y z w
    p_bc: [{p_bc[0]:.12f}, {p_bc[1]:.12f}, {p_bc[2]:.12f}] # x y z [m]
  noise: [
    0.5, 0.0,
    0.0, 0.5] # [pixel^2]
"""
    for L in [x for x in ("S", "M", "O") if os.path.exists(f"{W}/xrslam-wt-{x}")]:
        head_L = open(f"{W}/xrslam-wt-{L}/configs/iphonex.yaml").read().split('cam0:')[0]
        open(f"{D}/device_{L}.yaml", "w").write(head_L + cam0)
    json.dump(dict(p_bc=p_bc.tolist(), q_bc=q_bc.tolist(), K_half=Kp, n_frames=int(len(fr))), open(D + "/meta.json", "w"))
    # sign check of the accelerometer against the GT orientation (GT = camera pose in world):
    # world-frame specific force should be ~ +9.8 along one world axis (up) and ~0 on the others.
    from scipy.spatial.transform import Rotation as Rot  # noqa
    tq = tg[m][::10]; Aq = A[::10]
    i = np.clip(np.searchsorted(gt[:, 0], tq), 0, len(gt) - 1)
    Rwc = Rot.from_quat(np.c_[gt[i, 5], gt[i, 6], gt[i, 7], gt[i, 4]]).as_matrix()
    Rci = T_CAM_IMU[:3, :3]
    fw = np.einsum('nij,jk,nk->ni', Rwc, Rci, Aq)
    print("world specific force mean (should be ~[0,0,+9.8] or ~+9.8 on the GT up axis):", fw.mean(0).round(3),
          "|mean| =", np.linalg.norm(fw.mean(0)).round(3))


if __name__ == "__main__":
    main()
