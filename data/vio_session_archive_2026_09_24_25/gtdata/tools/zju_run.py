#!/usr/bin/env python3
"""ZJU-SenseTime VISLAM sequence -> XRSLAM S and M lineage replays, with ZERO image files on disk.

The official zip is downloaded into RAM (sha256 recorded), the small CSV/YAML members are converted
to EuRoC layout on disk, and the PNG frames are decoded (cv2.imdecode, IMREAD_UNCHANGED, exactly the
reader's own call) and streamed as raw 8-bit gray through a FIFO into pw_euroc_runner_stream
(stream-patched euroc_dataset_reader.cpp).  Device yaml = the tree's configs/iphonex.yaml with the
cam0 block replaced by the dataset's own camera/sensor.yaml calibration (IMU noise block unchanged:
upstream uses the identical noise block for EuRoC and iPhone X).

usage: zju_run.py SEQ [S,M]
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

import cv2
# NOTE: EuRoC CSVs must be CRLF: the player reader scans the header with "%[^\\r]\\r\\n" (euroc_dataset_reader.h:90)
import numpy as np

W = "/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata"
URL = "http://www.cad.zju.edu.cn/home/gfzhang/dataset/VISLAM-Dataset/{}.zip"


def free_gib():
    st = os.statvfs(os.path.expanduser("~"))
    return st.f_bavail * st.f_frsize / 2 ** 30


def parse_sensor_yaml(txt):
    d = {}
    for ln in txt.splitlines():
        ln = ln.split('#')[0].strip()
        if ':' in ln:
            k, v = ln.split(':', 1)
            d[k.strip()] = v.strip()
    return d


def vec(s):
    return [float(x) for x in s.strip('[] ').split(',')]


def qmat(q):
    x, y, z, w = q
    n = np.sqrt(x * x + y * y + z * z + w * w); x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def device_yaml(template, cam, res):
    intr = vec(cam['camera']); dist = vec(cam['distortion']); q = vec(cam['q']); p = vec(cam['p']); td = float(cam['t'])
    R = qmat(q)
    T = [R[0, 0], R[0, 1], R[0, 2], p[0], R[1, 0], R[1, 1], R[1, 2], p[1], R[2, 0], R[2, 1], R[2, 2], p[2]]
    head = template.split('cam0:')[0]
    flag = 0 if all(abs(v) < 1e-12 for v in dist) else 1
    cam0 = f"""cam0:
  # [gtdata] from the dataset's own camera/sensor.yaml ({cam.get('description', '')})
  T_BS:
    cols: 4
    rows: 4
    data: [{T[0]:.9f}, {T[1]:.9f}, {T[2]:.9f}, {T[3]:.9f},
           {T[4]:.9f}, {T[5]:.9f}, {T[6]:.9f}, {T[7]:.9f},
           {T[8]:.9f}, {T[9]:.9f}, {T[10]:.9f}, {T[11]:.9f},
           0.0, 0.0, 0.0, 1.0]
  resolution: [{res[0]}, {res[1]}]
  camera_model: pinhole
  distortion_model: radtan
  intrinsics: [{intr[0]}, {intr[1]}, {intr[2]}, {intr[3]}] # fu, fv, cu, cv
  camera_distortion_flag: {flag}
  distortion: [{dist[0]}, {dist[1]}, {dist[2]}, {dist[3]}] # k1, k2, p1, p2
  camera_readout_time: 0.0
  time_offset: {td}
  extrinsic:
    q_bc: [{q[0]}, {q[1]}, {q[2]}, {q[3]}] # x y z w
    p_bc: [{p[0]}, {p[1]}, {p[2]}] # x y z [m]
  noise: [
    0.5, 0.0,
    0.0, 0.5] # [pixel^2]
"""
    return head + cam0


def main():
    seq = sys.argv[1]
    lineages = (sys.argv[2] if len(sys.argv) > 2 else "S,M").split(',')
    D = f"{W}/ds/zju/{seq}"; os.makedirs(D + "/mav0/cam0", exist_ok=True); os.makedirs(D + "/mav0/imu0", exist_ok=True)
    R = f"{W}/runs/zju"; os.makedirs(R, exist_ok=True)
    fg = free_gib()
    print(f"[{seq}] free {fg:.2f} GiB before download", flush=True)
    if fg < 2.0:
        print("STOP: free < 2 GiB"); sys.exit(2)
    url = URL.format(seq)
    t0 = time.time()
    h = hashlib.sha256(); buf = io.BytesIO()
    with urllib.request.urlopen(url, timeout=300) as r:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            h.update(b); buf.write(b)
    size = buf.tell(); sha = h.hexdigest()
    rec = dict(dataset="ZJU-SenseTime VISLAM", seq=seq, url=url, bytes=size, sha256=sha,
               stored_on_disk=False, t_download_s=round(time.time() - t0, 1),
               date=time.strftime("%Y-%m-%d %H:%M:%S"))
    print(json.dumps(rec), flush=True)
    with open(f"{W}/ds/manifest.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    z = zipfile.ZipFile(buf)
    names = z.namelist()
    cy = [n for n in names if n.endswith('camera/sensor.yaml')]
    assert len(cy) == 1, cy
    pref = cy[0][:-len('camera/sensor.yaml')]
    rd = lambda n: z.read(pref + n).decode()
    cam = parse_sensor_yaml(rd('camera/sensor.yaml'))
    # camera csv -> EuRoC cam0/data.csv (t_ns, filename), sorted by t (reader stable_sorts by t)
    rows = []
    for ln in rd('camera/data.csv').splitlines():
        if ln.startswith('#') or not ln.strip():
            continue
        t, fn = ln.split(',')
        rows.append((int(round(float(t) * 1e9)), fn.strip()))
    rows.sort()
    with open(D + "/mav0/cam0/data.csv", "w", newline="\r\n") as f:
        f.write("#timestamp [ns],filename\n")
        for t, fn in rows:
            f.write(f"{t},{fn}\n")
    with open(D + "/mav0/imu0/data.csv", "w", newline="\r\n") as f:
        f.write("#timestamp [ns],w_RS_S_x [rad s^-1],w_RS_S_y [rad s^-1],w_RS_S_z [rad s^-1],a_RS_S_x [m s^-2],a_RS_S_y [m s^-2],a_RS_S_z [m s^-2]\n")
        for ln in rd('imu/data.csv').splitlines():
            if ln.startswith('#') or not ln.strip():
                continue
            v = ln.split(',')
            f.write(f"{int(round(float(v[0]) * 1e9))}," + ",".join(x.strip() for x in v[1:7]) + "\n")
    with open(D + "/gt.tum", "w") as f:  # groundtruth: t, qx qy qz qw, px py pz (body = IMU, extrinsic identity)
        for ln in rd('groundtruth/data.csv').splitlines():
            if ln.startswith('#') or not ln.strip():
                continue
            v = [float(x) for x in ln.split(',')]
            f.write(f"{v[0]:.9f} {v[5]:.6f} {v[6]:.6f} {v[7]:.6f} {v[1]:.9f} {v[2]:.9f} {v[3]:.9f} {v[4]:.9f}\n")
    for n in ['camera/sensor.yaml', 'imu/sensor.yaml', 'groundtruth/sensor.yaml', 'vicon/sensor.yaml']:
        open(D + "/" + n.replace('/', '_'), "w").write(rd(n))
    # probe first frame
    im0 = cv2.imdecode(np.frombuffer(z.read(pref + 'camera/images/' + rows[0][1]), np.uint8), cv2.IMREAD_UNCHANGED)
    print(f"[{seq}] frames {len(rows)} first {im0.shape} {im0.dtype}; cam {cam.get('description')}", flush=True)
    assert im0.ndim == 2 and im0.dtype == np.uint8, "expected 8-bit gray PNG"
    H, Wd = im0.shape
    for L in lineages:
        tmpl = open(f"{W}/xrslam-wt-{L}/configs/iphonex.yaml").read()
        dev = f"{D}/device_{L}.yaml"
        open(dev, "w").write(device_yaml(tmpl, cam, (Wd, H)))
        slam = f"{W}/cfg/slam_O.yaml" if L == "O" else f"{W}/xrslam-wt-{L}/configs/iphone_slam.yaml"
        out = f"{R}/{seq}.{L}.tum"
        extra = ["--pace", "1", "--camera-out", f"{R}/{seq}.{L}.cam.tum"] if L == "O" else []
        fifo = f"{W}/work/fifo_{seq}_{L}"
        if os.path.exists(fifo):
            os.remove(fifo)
        os.mkfifo(fifo)
        env = dict(os.environ, PW_RAW_STREAM=fifo, PW_RAW_W=str(Wd), PW_RAW_H=str(H))
        log = open(out + ".log", "w")
        p = subprocess.Popen([f"{W}/tools/locked.sh", f"{W}/work/build-{L}/pw_euroc_runner_stream", slam, dev,
                              f"euroc://{D}/mav0", out] + extra, env=env, stdout=log, stderr=subprocess.STDOUT)
        n = 0
        try:
            with open(fifo, "wb") as ff:
                for t, fn in rows:
                    im = cv2.imdecode(np.frombuffer(z.read(pref + 'camera/images/' + fn), np.uint8), cv2.IMREAD_UNCHANGED)
                    if im.ndim == 3:
                        im = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
                    assert im.shape == (H, Wd)
                    ff.write(np.ascontiguousarray(im).tobytes()); n += 1
        except BrokenPipeError:
            print(f"[{seq}/{L}] runner closed the stream after {n} frames", flush=True)
        rc = p.wait(); log.close()
        os.remove(fifo)
        npose = sum(1 for _ in open(out)) if os.path.exists(out) else 0
        print(f"[{seq}/{L}] rc={rc} fed={n}/{len(rows)} poses={npose} -> {out}", flush=True)
    del z, buf


if __name__ == "__main__":
    main()
