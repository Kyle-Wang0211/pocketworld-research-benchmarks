#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ARKitScenes raw -> BlendedMVS 目录格式 (datasets/blend.py 原样能读)。

每条规则的出处 (apple/ARKitScenes 仓 HEAD, 09-14 克隆到 /root/ARKitScenes):
  位姿     threedod/benchmark_scripts/utils/tenFpsDataLoader.py:13-44 TrajStringToMatrix
           traj 行 = ts, axis-angle(r_w_to_p), t(w_to_p); extrinsics=[R|t] 是 world->camera;
           官方 Rt = inv(extrinsics) = camera->world。 MVSNet cam.txt 要 world->camera => 写 inv(Rt)=extrinsics
  帧↔位姿   tenFpsDataLoader.py:332-336: 精确键, 否则 |Δt| < 0.005 s
  内参     tenFpsDataLoader.py st2_camera_intrinsics: .pincam = w h fx fy cx cy; 找不到时 ±0.001 s (257-263)
  深度     tenFpsDataLoader.py: frame["depth"] / 1000.0  (uint16 mm -> m); 0 = 无效
  深度→图  DUSt3R datasets_preprocess/preprocess_arkitscenes.py: cv2.resize(depth,(W,H),INTER_NEAREST_EXACT)
           (与 tartanair_to_blend.py:164 同用 NEAREST)
  关键帧   deep-video-mvs dvmvs/keyframe_buffer.py try_new_keyframe:
           combined pose_distance(上一关键帧, 当前) >= keyframe_pose_distance 才收;
           常数 dvmvs/config.py: test_keyframe_pose_distance = 0.1
  其余     逐字导入 tartanair_to_blend.py: pose_distance/calculate_penalty (deep-video-mvs),
           write_pairs, frame_range (colmap2mvsnet 1%/99%), 640x480 -> 768x576 图 INTER_AREA / 深度 NEAREST / K 同比,
           write_pfm, rotation_is_valid, cross_view_check (自证)
"""
import argparse, os, sys, glob
import numpy as np, cv2
sys.path.insert(0, "/root/ta2")
from tartanair_to_blend import (pose_distance, write_pfm, rotation_is_valid,
                                cross_view_check, write_pairs, frame_range)

KEYFRAME_POSE_DISTANCE = 0.1     # dvmvs/config.py test_keyframe_pose_distance
TOL_POSE = 0.005                 # tenFpsDataLoader.py:335
TOL_INTR = 0.001                 # tenFpsDataLoader.py:260,263


def traj_line(line):
    """TrajStringToMatrix 逐字: 返回 (ts, Rt=camera->world)"""
    t = line.split()
    assert len(t) == 7, line
    R, _ = cv2.Rodrigues(np.asarray([float(x) for x in t[1:4]]))
    E = np.eye(4, dtype=np.float64)
    E[:3, :3] = R
    E[:3, 3] = [float(x) for x in t[4:7]]
    return float(t[0]), np.linalg.inv(E)


def ts_str(path):
    """'{vid}_{ts}.png' -> 'ts' 原始字符串 (不重新格式化, 避免浮点改名)"""
    b = os.path.basename(path)
    return b.split("_", 1)[1].rsplit(".", 1)[0]


def read_pincam(p):
    w, h, fx, fy, cx, cy = np.loadtxt(p)
    return (int(w), int(h)), np.array([[fx, 0, cx], [0, fy, cy], [0, 0, 1.0]])


def convert_video(vd, vid, out_root, a):
    traj = [traj_line(l) for l in open(os.path.join(vd, "lowres_wide.traj")) if l.strip()]
    traj_ts = np.array([t for t, _ in traj])
    imgs = sorted(glob.glob(os.path.join(vd, "vga_wide", "*.png")), key=lambda p: float(ts_str(p)))
    st = dict(imgs=len(imgs), no_pose=0, no_depth=0, no_intr=0, bad_R=0, tol_pose=0, tol_intr=0)
    frames = []
    for ip in imgs:
        s = ts_str(ip)
        ts = float(s)
        k = int(np.argmin(np.abs(traj_ts - ts)))
        dt = abs(traj_ts[k] - ts)
        if dt >= TOL_POSE:
            st["no_pose"] += 1
            continue
        if dt > 1e-9:
            st["tol_pose"] += 1
        dp = os.path.join(vd, "lowres_depth", "%s_%s.png" % (vid, s))
        if not os.path.exists(dp):
            st["no_depth"] += 1
            continue
        pc = None
        for cand in (s, "%.3f" % (ts - TOL_INTR), "%.3f" % (ts + TOL_INTR)):
            p = os.path.join(vd, "vga_wide_intrinsics", "%s_%s.pincam" % (vid, cand))
            if os.path.exists(p):
                pc = p
                if cand != s:
                    st["tol_intr"] += 1
                break
        if pc is None:
            st["no_intr"] += 1
            continue
        T = traj[k][1]
        ok, _ = rotation_is_valid(T[:3, :3])
        if not ok:
            st["bad_R"] += 1
            continue
        frames.append((ts, ip, dp, pc, T))
    # 关键帧 (deep-video-mvs 规则)
    kf = []
    for fr in frames:
        if not kf or pose_distance(kf[-1][4], fr[4])[0] >= KEYFRAME_POSE_DISTANCE:
            kf.append(fr)
    st["with_pose"] = len(frames)
    st["keyframes"] = len(kf)
    if len(kf) < a.min_frames:
        print("  SKIP %s: 关键帧 %d < %d  %s" % (vid, len(kf), a.min_frames, st), flush=True)
        return None
    # 读图/深度/内参
    poses, depths, Ks, imgs_out = [], [], [], []
    for ts, ip, dp, pc, T in kf:
        (w, h), K = read_pincam(pc)
        assert (w, h) == (640, 480), (pc, w, h)
        K = K.copy()
        K[0] *= a.out_w / float(w)
        K[1] *= a.out_h / float(h)
        d = cv2.imread(dp, cv2.IMREAD_UNCHANGED)
        assert d is not None and d.dtype == np.uint16, dp
        d = d.astype(np.float32) / 1000.0
        d = cv2.resize(d, (a.out_w, a.out_h), interpolation=cv2.INTER_NEAREST)
        img = cv2.imread(ip, cv2.IMREAD_COLOR)
        assert img.shape[:2] == (h, w), ip
        img = cv2.resize(img, (a.out_w, a.out_h), interpolation=cv2.INTER_AREA)
        poses.append(T); depths.append(d); Ks.append(K); imgs_out.append(img)
    r_ok = cross_view_check(poses, depths, Ks[0])
    r_flip = cross_view_check([np.linalg.inv(T) for T in poses], depths, Ks[0])   # 阴性对照: 位姿写反
    scan = "ak_%s" % vid
    print("  %s: 图 %d | 有位姿 %d | 关键帧 %d | 跨视中位|dz| 正确 %.4f m / 写反 %.4f m | %s"
          % (scan, st["imgs"], st["with_pose"], st["keyframes"], r_ok, r_flip,
             {k: st[k] for k in ("no_pose", "no_depth", "no_intr", "bad_R", "tol_pose", "tol_intr")}), flush=True)
    if a.dry:
        return st
    for sub in ("blended_images", "cams", "rendered_depth_maps"):
        os.makedirs(os.path.join(out_root, scan, sub), exist_ok=True)
    for j, (T, d, K, img) in enumerate(zip(poses, depths, Ks, imgs_out)):
        cv2.imwrite(os.path.join(out_root, scan, "blended_images", "%08d.jpg" % j), img,
                    [cv2.IMWRITE_JPEG_QUALITY, 95])
        write_pfm(os.path.join(out_root, scan, "rendered_depth_maps", "%08d.pfm" % j), d)
        E = np.linalg.inv(T)                                  # world->camera = 官方 extrinsics
        fr = frame_range(d)
        if fr is None:
            fr = (0.1, 100.0)
        with open(os.path.join(out_root, scan, "cams", "%08d_cam.txt" % j), "w") as f:
            f.write("extrinsic\n")
            for rr in range(4):
                f.write(" ".join("%.9f" % E[rr, c] for c in range(4)) + "\n")
            f.write("\nintrinsic\n")
            for rr in range(3):
                f.write(" ".join("%.9f" % K[rr, c] for c in range(3)) + "\n")
            f.write("\n%.6f %.6f\n" % fr)
    write_pairs(os.path.join(out_root, scan, "cams", "pair.txt"), poses, a.nsrc)
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="…/raw/Training 或 …/raw/Validation")
    ap.add_argument("--out", required=True)
    ap.add_argument("--vids", nargs="*", default=None, help="默认: raw 下全部 video_id")
    ap.add_argument("--nsrc", type=int, default=10)          # 与 tartanair_to_blend.py 同
    ap.add_argument("--out_w", type=int, default=768)
    ap.add_argument("--out_h", type=int, default=576)
    ap.add_argument("--min_frames", type=int, default=12)    # 与 tartanair_to_blend.py 同
    ap.add_argument("--dry", action="store_true", help="只统计+自证, 不写盘")
    a = ap.parse_args()
    vids = a.vids or sorted(d for d in os.listdir(a.raw) if os.path.isdir(os.path.join(a.raw, d)))
    n = 0
    for vid in vids:
        vd = os.path.join(a.raw, vid)
        if not os.path.isfile(os.path.join(vd, "lowres_wide.traj")):
            print("  SKIP %s: 无 lowres_wide.traj" % vid, flush=True)
            continue
        if os.path.isfile(os.path.join(a.out, "ak_%s" % vid, "cams", "pair.txt")):
            n += 1
            continue
        if convert_video(vd, vid, a.out, a) is not None:
            n += 1
    print("DONE: %d scans in %s" % (n, a.out), flush=True)


if __name__ == "__main__":
    main()
