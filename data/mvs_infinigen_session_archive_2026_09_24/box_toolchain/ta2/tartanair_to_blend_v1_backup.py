#!/usr/bin/env python3
"""TartanAir V2 -> BlendedMVS 目录格式(datasets/blend.py 原样能读)。

结构(实测 pilot 下载所见):
  <env>/Data_{easy,hard}/P###/image_lcam_front/{:06d}_lcam_front.png
  <env>/Data_{easy,hard}/P###/depth_lcam_front/{:06d}_lcam_front_depth.png
  <env>/Data_{easy,hard}/P###/pose_lcam_front.txt   每行 7 个数 = x y z qx qy qz qw (NED)

三处约定全部抄自 TartanAir 官方工具箱 tartanair/customizer.py:586-604 与 reader.py:42-44:
  NED_R_cam = [[0,0,1],[1,0,0],[0,1,0]]
  world_T_cam[:3,:3] = Rotation.from_quat(pose[3:]).as_matrix() @ NED_R_cam
  world_T_cam[:3, 3] = pose[:3]
  K(640x640) = [[320,0,319.5],[0,320,319.5],[0,0,1]]
  深度 png 是 RGBA8, 直接 .view("<f4") 重解释成 float32

分辨率: TartanAir 是 640x640 方图, 目标 768x576 是 4:3。
直接 resize 会改变长宽比 => 先中心裁 640x480(4:3) 再缩放, K 随之改。

深度是不是平面 Z: customizer.py 把 depthmap 直接喂给 depthmap_to_absolute_camera_coordinates
(该函数按 X=(u-cx)*z/fx 反投, 即平面 Z)。但我们不靠读代码定论 ——
cross_view_check 是判据: 若实际是射线距离, 跨视残差会爆掉。
"""
import argparse, os, sys, glob
import numpy as np, cv2
from scipy.spatial.transform import Rotation

OPTIMAL_T, OPTIMAL_R, DEGREE = 0.15, 0.0, 2.0

# ---- 以下三个函数逐字取自 deep-video-mvs (MIT), 与 Hypersim 转换器同一份 ----
def pose_distance(reference_pose, measurement_pose):
    rel_pose = np.dot(np.linalg.inv(reference_pose), measurement_pose)
    R = rel_pose[:3, :3]; t = rel_pose[:3, 3]
    R_measure = np.sqrt(2 * (1 - min(3.0, np.trace(R)) / 3))
    t_measure = np.linalg.norm(t)
    return np.sqrt(t_measure ** 2 + R_measure ** 2), R_measure, t_measure

def calculate_penalty(t_score, R_score):
    R_penalty = np.abs(R_score - OPTIMAL_R) ** DEGREE
    t_diff = t_score - OPTIMAL_T
    t_penalty = (5.0 * np.abs(t_diff) ** DEGREE) if t_diff < 0.0 else np.abs(t_diff) ** DEGREE
    return R_penalty + t_penalty

def write_pfm(path, image):
    image = np.flipud(np.asarray(image, dtype=np.float32))
    with open(path, "wb") as f:
        f.write(b"Pf\n"); f.write(b"%d %d\n" % (image.shape[1], image.shape[0])); f.write(b"-1.0\n")
        image.tofile(f)

def rotation_is_valid(R):
    R = np.asarray(R, dtype=np.float64)
    if R.shape != (3, 3) or not np.isfinite(R).all(): return False, "non-finite"
    try: Rotation.from_matrix(R)
    except Exception as e: return False, f"scipy: {str(e)[:60]}"
    resid = float(np.abs(R.T @ R - np.eye(3)).max()); det = float(np.linalg.det(R))
    if resid > 1e-3 or det < 0.0: return False, f"orthonormality resid {resid:.3g}, det {det:.3f}"
    return True, ""

def cross_view_check(poses, depths, K, n=6):
    Ki = np.linalg.inv(K); res = []
    idx = list(range(0, len(poses), max(1, len(poses) // n)))[:n]
    for i in idx:
        j = i + 1 if i + 1 < len(poses) else i - 1
        if j < 0: continue
        di, dj = depths[i], depths[j]
        H, W = di.shape
        ys, xs = np.mgrid[0:H:16, 0:W:16]
        z = di[ys, xs]; m = z > 0
        if m.sum() < 50: continue
        uv = np.stack([xs[m], ys[m], np.ones(m.sum())])
        cam_i = Ki @ (uv * z[m])
        Tji = np.linalg.inv(poses[j]) @ poses[i]
        cam_j = Tji[:3, :3] @ cam_i + Tji[:3, 3:4]
        good = cam_j[2] > 1e-6
        p = K @ cam_j[:, good]
        u = (p[0] / p[2]).round().astype(int); v = (p[1] / p[2]).round().astype(int)
        ok = (u >= 0) & (u < W) & (v >= 0) & (v < H)
        if ok.sum() < 50: continue
        zj = dj[v[ok], u[ok]]; valid = zj > 0
        if valid.sum() < 50: continue
        res.append(np.median(np.abs(cam_j[2, good][ok][valid] - zj[valid])))
    return float(np.median(res)) if res else float("inf")

def write_pairs(path, poses, nsrc):
    n = len(poses)
    with open(path, "w") as f:
        f.write(f"{n}\n")
        for i in range(n):
            pen = []
            for j in range(n):
                if i == j: continue
                _, R_m, t_m = pose_distance(poses[i], poses[j])
                pen.append((calculate_penalty(t_m, R_m), j))
            pen.sort()
            sel = pen[:nsrc]
            f.write(f"{i}\n{len(sel)} " + " ".join(f"{j} {1.0/(1.0+p):.4f}" for p, j in sel) + "\n")

# ------------------------------------------------------------------ TartanAir 专有
NED_R_CAM = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], dtype=np.float64)   # customizer.py:586
K_RAW = np.array([[320.0, 0, 319.5], [0, 320.0, 319.5], [0, 0, 1.0]])       # customizer.py:600

def read_depth_png(p):
    """reader.py:42-44 —— RGBA8 直接 view 成 float32"""
    rgba = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    if rgba is None: return None
    return np.squeeze(rgba.view("<f4"), axis=-1)

def world_T_cam(row):
    """customizer.py:594-596"""
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = Rotation.from_quat(row[3:]).as_matrix() @ NED_R_CAM
    T[:3, 3] = row[:3]
    return T

def frame_range(d):
    """逐图像深度范围, 抄 MVSNet 官方 colmap2mvsnet.py 的 1%/99%"""
    v = d[np.isfinite(d) & (d > 0)]
    if v.size < 100: return None
    s = np.sort(v.ravel())
    return float(s[int(len(s) * .01)]), float(s[int(len(s) * .99)])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/root/ta2")
    ap.add_argument("--out", default="/root/ta2/blendfmt")
    ap.add_argument("--envs", nargs="+", required=True)
    ap.add_argument("--nsrc", type=int, default=10)
    ap.add_argument("--out_w", type=int, default=768)
    ap.add_argument("--out_h", type=int, default=576)
    ap.add_argument("--stride", type=int, default=1, help="帧抽样步长, 控制总组数")
    ap.add_argument("--min_frames", type=int, default=12)
    a = ap.parse_args()

    # 640x640 -> 中心裁 640x480 -> 缩放到 out_w x out_h
    CROP_H = 480
    y0 = (640 - CROP_H) // 2
    K = K_RAW.copy(); K[1, 2] -= y0                       # 裁剪只动 cy
    K[0] *= a.out_w / 640.0; K[1] *= a.out_h / float(CROP_H)

    n_scan = 0
    for env in a.envs:
        for diff in ("Data_easy", "Data_hard"):
            for traj in sorted(glob.glob(os.path.join(a.root, env, diff, "P*"))):
                pose_f = os.path.join(traj, "pose_lcam_front.txt")
                imgd = os.path.join(traj, "image_lcam_front")
                depd = os.path.join(traj, "depth_lcam_front")
                if not (os.path.exists(pose_f) and os.path.isdir(imgd)): continue
                rows = np.loadtxt(pose_f, dtype=np.float64)
                if rows.ndim != 2 or rows.shape[1] != 7: continue
                imgs = sorted(glob.glob(os.path.join(imgd, "*.png")))
                if len(imgs) != len(rows):
                    print(f"  SKIP {env}/{diff}/{os.path.basename(traj)}: "
                          f"图 {len(imgs)} != 位姿 {len(rows)}", flush=True); continue

                keep, poses, depths, colors, bad = [], [], [], [], 0
                for i in range(0, len(imgs), a.stride):
                    T = world_T_cam(rows[i])
                    ok, why = rotation_is_valid(T[:3, :3])
                    if not ok: bad += 1; continue
                    dp = os.path.join(depd, f"{i:06d}_lcam_front_depth.png")
                    if not os.path.exists(dp): continue
                    d = read_depth_png(dp)
                    if d is None: continue
                    d = d[y0:y0 + CROP_H]                                   # 裁
                    d = cv2.resize(d, (a.out_w, a.out_h), interpolation=cv2.INTER_NEAREST)
                    d[~np.isfinite(d)] = 0.0
                    keep.append(imgs[i]); poses.append(T); depths.append(d); colors.append(dp)
                if len(keep) < a.min_frames:
                    print(f"  SKIP {env}/{diff}/{os.path.basename(traj)}: 有效帧 {len(keep)}", flush=True)
                    continue

                r = cross_view_check(poses, depths, K)
                scan = f"{env}_{diff.replace('Data_','')}_{os.path.basename(traj)}"
                print(f"  {scan}: {len(keep)} 帧 | bad-R 丢 {bad} | 跨视中位|dz| {r:.4f} m", flush=True)

                for sub in ("blended_images", "cams", "rendered_depth_maps"):
                    os.makedirs(os.path.join(a.out, scan, sub), exist_ok=True)
                for j, (ip, T, d) in enumerate(zip(keep, poses, depths)):
                    img = cv2.imread(ip, cv2.IMREAD_COLOR)[y0:y0 + CROP_H]
                    img = cv2.resize(img, (a.out_w, a.out_h), interpolation=cv2.INTER_AREA)
                    cv2.imwrite(os.path.join(a.out, scan, "blended_images", f"{j:08d}.jpg"),
                                img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    write_pfm(os.path.join(a.out, scan, "rendered_depth_maps", f"{j:08d}.pfm"), d)
                    E = np.linalg.inv(T)
                    fr = frame_range(d)
                    if fr is None: fr = (0.1, 100.0)
                    with open(os.path.join(a.out, scan, "cams", f"{j:08d}_cam.txt"), "w") as f:
                        f.write("extrinsic\n")
                        for rr in range(4): f.write(" ".join(f"{E[rr,c]:.9f}" for c in range(4)) + "\n")
                        f.write("\nintrinsic\n")
                        for rr in range(3): f.write(" ".join(f"{K[rr,c]:.9f}" for c in range(3)) + "\n")
                        f.write(f"\n{fr[0]:.6f} {fr[1]:.6f}\n")
                write_pairs(os.path.join(a.out, scan, "cams", "pair.txt"), poses, a.nsrc)
                n_scan += 1
    print(f"DONE: wrote {n_scan} scans to {a.out}", flush=True)

if __name__ == "__main__":
    main()
