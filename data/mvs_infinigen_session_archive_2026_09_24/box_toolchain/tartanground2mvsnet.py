#!/usr/bin/env python3.11
"""
tartanground2mvsnet.py

将 TartanGround 单条轨迹单相机的原始数据(image PNG + depth PNG(RGBA float32) +
pose_lcam_front.txt)转换成 CasDiffMVS 官方训练 dataloader
(datasets/blend.py 的 MVSDataset, --dataset=blend)可以直接读取的目录布局:

    {out_root}/{scan}/blended_images/{:08d}.jpg
    {out_root}/{scan}/cams/{:08d}_cam.txt
    {out_root}/{scan}/cams/pair.txt
    {out_root}/{scan}/rendered_depth_maps/{:08d}.pfm
    {out_root}/lists/train.txt   (单行 = scan 名)

铁律:不自研共视分数算法。视角选择分数 100% 复刻官方公式:
    score(i,j) = sum_{p in shared} exp(-(theta-theta0)^2 / (2*sigma^2))
    theta0=5, sigma1=1 (theta<=theta0), sigma2=10 (theta>theta0)
出处:
  - 上游权威实现: YoYo000/MVSNet colmap2mvsnet.py::calc_score
    (经 WebFetch 于 2026-08-24 核实,https://github.com/YoYo000/MVSNet/blob/master/mvsnet/colmap2mvsnet.py)
  - 本机已vendor且经用户验证与上游逐字节等价的副本:
    /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs/colmap_input.py:374-397
    (theta0/sigma1/sigma2 默认值见同文件 argparse, line ~251-253: theta0=5, sigma1=1, sigma2=10)

TartanGround 没有 COLMAP 稀疏点云(id_intersect 的原始来源),因此本转换器用
"深度真值反投影 + 官方 filter.py 的几何一致性判据" 替代 colmap 稀疏点交集来确定
"共视点集合",分数公式本身逐字不改:
  - 几何一致性判据(reproject_with_depth / check_geometric_consistency)与其默认阈值
    geo_pixel_thres=1.0, geo_depth_thres=0.01 100% 复用自同一份官方 filter.py:
    /Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs/filter.py:8-104
    (该文件本身就是本仓库测试期深度融合所用的官方逻辑,这里只是在数据准备阶段复用,而非另造一套)

位姿坐标系转换(TartanGround pose_*.txt 是 NED 相机系: x-前 y-右 z-下,
且 world 也是 NED)→ 标准 CV 相机系(x-右 y-下 z-前)100% 复刻官方 ned2cam:
    /Users/kaidongwang/Developer/tartanground_b_line/tartanair_tools/evaluation/trajectory_transform.py:21-35
    T = [[0,1,0,0],[0,0,1,0],[1,0,0,0],[0,0,0,1]]; ttt = T @ SE(pose) @ inv(T)

内参 fx=fy=W/2, cx=W/2, cy=H/2 (方形图像, FOV=90 deg, 光心在图像中心)出处:
    /Users/kaidongwang/Developer/tartanground_b_line/tartanairpy/tartanair/reader.py
    depth_to_dist() 中的注释 "assume: fov = 90 on both x and y axes, and
    optical center is at image center", f = ww/2 (约 line 131-153)
    W=H=640 由本机实际下载的 Office/Data_omni/P0000/image_lcam_front 逐张验证 (640x640 PNG)。

Depth PNG -> float32 米制 z-depth 的 RGBA bit-reinterpret 解码复刻自:
    /Users/kaidongwang/Developer/tartanground_b_line/tartanairpy/tartanair/reader.py
    depth_rgba_float32() / read_depth() (约 line 41-65)
"""
import argparse
import glob
import os
import sys
import json

import cv2
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation

# 复用官方 vendored 的 pfm 写出函数,保证字节格式与训练 dataloader 完全一致
DIFFMVS_DIR = os.environ.get("DIFFMVS_DIR",
    "/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs")
print("[DIFFMVS_DIR]", DIFFMVS_DIR, "exists=", os.path.isdir(DIFFMVS_DIR), flush=True)
sys.path.insert(0, DIFFMVS_DIR)
from datasets.data_io import save_pfm  # noqa: E402

# ---------------------------------------------------------------------------
# 官方 view-selection score 参数(colmap_input.py argparse 默认值,line 251-253)
THETA0 = 5.0
SIGMA1 = 1.0
SIGMA2 = 10.0

# 官方 filter.py check_geometric_consistency 默认阈值(line 73-74)
GEO_PIXEL_THRES = 1.0
GEO_DEPTH_THRES = 0.01

# NED -> CV 相机系转换矩阵,逐字复刻 trajectory_transform.py:24-27 的 ned2cam()
T_NED2CAM = np.array([
    [0, 1, 0, 0],
    [0, 0, 1, 0],
    [1, 0, 0, 0],
    [0, 0, 0, 1],
], dtype=np.float64)
T_NED2CAM_INV = np.linalg.inv(T_NED2CAM)


def load_poses_ned(pose_file):
    """pose_lcam_front.txt: 每行 'tx ty tz qx qy qz qw' (NED world + NED cam axes)."""
    raw = np.loadtxt(pose_file)
    assert raw.ndim == 2 and raw.shape[1] == 7, raw.shape
    return raw


def pose_row_to_SE3(row):
    """[tx,ty,tz,qx,qy,qz,qw] -> 4x4 camera-to-world (body-to-world) 矩阵."""
    t = row[:3]
    q = row[3:7]  # xyzw, scipy 原生顺序
    R = Rotation.from_quat(q).as_matrix()
    SE = np.eye(4, dtype=np.float64)
    SE[:3, :3] = R
    SE[:3, 3] = t
    return SE


def ned_pose_to_cv_cam2world(row):
    """
    复刻 evaluation/trajectory_transform.py::ned2cam 的做法:
    对整条轨迹的每一帧同一个 T 做相似变换 T @ SE @ T^-1,
    把 NED 世界系+NED 相机系,同步转换成 (旋转后的世界系) + 标准 CV 相机系
    (x-右 y-下 z-前)。MVS 只关心相机间相对几何,全局旋转不影响结果。
    """
    SE_ned = pose_row_to_SE3(row)
    SE_cv = T_NED2CAM @ SE_ned @ T_NED2CAM_INV
    return SE_cv  # camera-to-world, 标准 CV 相机系


def decode_depth_png(path):
    """
    AirSim DepthPlanar 存成 RGBA8 PNG,4 个字节按小端 reinterpret 成 float32 米制
    z-depth(沿光轴,不是欧氏距离)。复刻 tartanairpy/tartanair/reader.py
    depth_rgba_float32()/read_depth() 的 else 分支。
    """
    raw = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise FileNotFoundError(path)
    assert raw.ndim == 3 and raw.shape[2] == 4, f"unexpected depth png shape {raw.shape}"
    depth = np.squeeze(raw.view("<f4"), axis=-1)
    return depth.astype(np.float32)


def reproject_with_depth(depth_ref, K_ref, E_ref, depth_src, K_src, E_src):
    """逐字复刻 filter.py::reproject_with_depth (仅去掉未使用的可选返回值)."""
    width, height = depth_ref.shape[1], depth_ref.shape[0]
    x_ref, y_ref = np.meshgrid(np.arange(0, width), np.arange(0, height))
    x_ref, y_ref = x_ref.reshape([-1]), y_ref.reshape([-1])
    xyz_ref = np.matmul(
        np.linalg.inv(K_ref),
        np.vstack((x_ref, y_ref, np.ones_like(x_ref))) * depth_ref.reshape([-1])
    )
    xyz_src = np.matmul(np.matmul(E_src, np.linalg.inv(E_ref)),
                         np.vstack((xyz_ref, np.ones_like(x_ref))))[:3]
    K_xyz_src = np.matmul(K_src, xyz_src)
    xy_src = K_xyz_src[:2] / K_xyz_src[2:3]
    x_src = xy_src[0].reshape([height, width]).astype(np.float32)
    y_src = xy_src[1].reshape([height, width]).astype(np.float32)
    sampled_depth_src = cv2.remap(depth_src, x_src, y_src, interpolation=cv2.INTER_LINEAR)

    xyz_src2 = np.matmul(
        np.linalg.inv(K_src),
        np.vstack((xy_src, np.ones_like(x_ref))) * sampled_depth_src.reshape([-1])
    )
    xyz_reproj = np.matmul(np.matmul(E_ref, np.linalg.inv(E_src)),
                            np.vstack((xyz_src2, np.ones_like(x_ref))))[:3]
    depth_reproj = xyz_reproj[2].reshape([height, width]).astype(np.float32)
    K_xyz_reproj = np.matmul(K_ref, xyz_reproj)
    K_xyz_reproj = np.where(K_xyz_reproj == 0, 1e-5, K_xyz_reproj)
    xy_reproj = K_xyz_reproj[:2] / K_xyz_reproj[2:3]
    xy_reproj = np.clip(xy_reproj, -1e8, 1e8)
    x_reproj = xy_reproj[0].reshape([height, width]).astype(np.float32)
    y_reproj = xy_reproj[1].reshape([height, width]).astype(np.float32)
    return depth_reproj, x_reproj, y_reproj


def check_geometric_consistency(depth_ref, K_ref, E_ref, depth_src, K_src, E_src,
                                 depth_min, depth_max):
    """逐字复刻 filter.py::check_geometric_consistency 默认阈值分支。"""
    width, height = depth_ref.shape[1], depth_ref.shape[0]
    x_ref, y_ref = np.meshgrid(np.arange(0, width), np.arange(0, height))
    depth_reproj, x2d_reproj, y2d_reproj = reproject_with_depth(
        depth_ref, K_ref, E_ref, depth_src, K_src, E_src)
    dist = np.sqrt((x2d_reproj - x_ref) ** 2 + (y2d_reproj - y_ref) ** 2)
    depth_diff = np.abs(depth_reproj - depth_ref)
    relative_depth_diff = depth_diff / np.maximum(depth_ref, 1e-6)
    mask = np.logical_and(dist < GEO_PIXEL_THRES, relative_depth_diff < GEO_DEPTH_THRES)
    mask2 = np.logical_and(depth_ref > depth_min, depth_ref < depth_max)
    mask = np.logical_and(mask, mask2)
    return mask


def calc_score_from_points(cam_center_i, cam_center_j, pts_world):
    """逐字复刻 colmap_input.py::calc_score 的角度-高斯打分公式部分(输入换成
    深度反投影得到的共视 3D 点集合,而不是 colmap 稀疏点)。"""
    if len(pts_world) == 0:
        return 0.0
    vi = cam_center_i[None, :] - pts_world
    vj = cam_center_j[None, :] - pts_world
    num = np.sum(vi * vj, axis=1)
    den = np.linalg.norm(vi, axis=1) * np.linalg.norm(vj, axis=1)
    den = np.maximum(den, 1e-12)
    cos_theta = np.clip(num / den, -1.0, 1.0)
    theta = np.degrees(np.arccos(cos_theta))
    sigma = np.where(theta <= THETA0, SIGMA1, SIGMA2)
    score = np.exp(-(theta - THETA0) ** 2 / (2 * sigma ** 2))
    return float(np.sum(score))


def cam_center_from_E(E):
    """E = world-to-camera 4x4. 相机中心 = -R^T t (与 colmap_input.py 一致)."""
    R = E[:3, :3]
    t = E[:3, 3]
    return -R.T @ t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image_dir", required=True, help="解压后的 image_lcam_front 目录")
    ap.add_argument("--depth_dir", required=True, help="解压后的 depth_lcam_front 目录")
    ap.add_argument("--pose_file", required=True, help="pose_lcam_front.txt")
    ap.add_argument("--out_root", required=True)
    ap.add_argument("--scan_name", default="tartanground_office_p0000_lcamfront")
    ap.add_argument("--stride", type=int, default=5, help="按此步长从轨迹中抽帧 (无出处, v2 不用; keyframe_dist>0 时忽略)")
    ap.add_argument("--max_frames", type=int, default=0, help="0 = 不截断 (v2); 旧值 150 无出处")
    ap.add_argument("--keyframe_dist", type=float, default=0.0,
                    help=">0: deep-video-mvs 关键帧规则 (config.py test_keyframe_pose_distance=0.1)")
    ap.add_argument("--min_frames", type=int, default=8, help="= blend.py:41 nviews 8 的最低帧数")
    ap.add_argument("--score_grid", type=int, default=0,
                    help=">0: 共视分数用步长 score_grid 的规则网格像素 (8 = CasDiffMVS stage1 1/8 分辨率, blend.py:127); 0 = 旧的随机 score_sample_pixels")
    ap.add_argument("--frame_ids_json", default=None,
                     help="(可选) JSON 文件,内容是轨迹内帧号的整数列表;给了就覆盖 "
                          "--stride/--max_frames,按该列表逐帧转换。用于按纹理分数选帧。")
    ap.add_argument("--out_w", type=int, default=0,
                     help="(可选) 输出宽度。默认 0 = 保持原生分辨率不动(与旧行为逐字节一致)。"
                          "给非 0 时:先中心裁剪到与 out_w:out_h 相同的宽高比,再各向同性缩放到 "
                          "out_w x out_h,内参同步变换。用于与 BlendedMVG 的图像尺寸对齐 —— "
                          "blend.py 全程不 resize,默认 collate 要求同 batch 内形状一致。")
    ap.add_argument("--out_h", type=int, default=0, help="(可选) 输出高度,见 --out_w")
    ap.add_argument("--num_src", type=int, default=10, help="pair.txt 每个 ref 保留的 src 数 (colmap2mvsnet sorted_score[:10])")
    ap.add_argument("--pair_rule", choices=["score", "dvmvs"], default="score",
                    help="score = colmap2mvsnet 角度分数(需稠密重投影, 长轨迹不可行); "
                         "dvmvs = deep-video-mvs 罚分 1/(1+penalty), 与 tartanair_to_blend.write_pairs 同式, 只用位姿")
    ap.add_argument("--score_sample_pixels", type=int, default=4000,
                     help="计算共视分数时,每对视角最多采样的一致像素点数(性能)")
    ap.add_argument("--depth_num_field", type=int, default=192,
                     help="cam.txt 深度行的 depth_num 字段(仅用于兼容展示,"
                          "blend.py 只读取该行首尾两个 token)")
    args = ap.parse_args()

    poses = load_poses_ned(args.pose_file)
    n_total = poses.shape[0]
    print(f"[info] 轨迹总帧数 = {n_total}")

    if args.frame_ids_json:
        with open(args.frame_ids_json) as fh:
            frame_ids = json.load(fh)
        assert isinstance(frame_ids, list) and frame_ids, args.frame_ids_json
        frame_ids = sorted(int(x) for x in frame_ids)
        assert frame_ids[0] >= 0 and frame_ids[-1] < n_total, \
            f"帧号越界: {frame_ids[0]}..{frame_ids[-1]} 不在 [0,{n_total})"
        if args.max_frames > 0:
            frame_ids = frame_ids[:args.max_frames]
        print(f"[info] 按 {args.frame_ids_json} 选帧 -> {len(frame_ids)} 帧: "
              f"{frame_ids[0]}..{frame_ids[-1]}")
    elif args.keyframe_dist > 0:
        # deep-video-mvs keyframe_buffer.py try_new_keyframe: 与上一关键帧 combined pose_distance >= 阈值才收
        sys.path.insert(0, "/root/ta2")
        from tartanair_to_blend import pose_distance
        frame_ids, last = [], None
        for i in range(n_total):
            T = ned_pose_to_cv_cam2world(poses[i])   # 与逐帧写 cam.txt 同一函数 (c2w, CV 相机系)
            if last is None or pose_distance(last, T)[0] >= args.keyframe_dist:
                frame_ids.append(i); last = T
        print(f"[info] dvmvs 关键帧 (>= {args.keyframe_dist}) -> {len(frame_ids)}/{n_total} 帧")
    else:
        frame_ids = list(range(0, n_total, args.stride))
        if args.max_frames > 0: frame_ids = frame_ids[:args.max_frames]
        print(f"[info] 抽帧 stride={args.stride} -> 选中 {len(frame_ids)} 帧: "
              f"{frame_ids[0]}..{frame_ids[-1]}")
    if len(frame_ids) < args.min_frames:
        print(f"[SKIP] 帧数 {len(frame_ids)} < min_frames {args.min_frames}"); sys.exit(3)

    scan_dir = os.path.join(args.out_root, args.scan_name)
    img_out_dir = os.path.join(scan_dir, "blended_images")
    cam_out_dir = os.path.join(scan_dir, "cams")
    depth_out_dir = os.path.join(scan_dir, "rendered_depth_maps")
    os.makedirs(img_out_dir, exist_ok=True)
    os.makedirs(cam_out_dir, exist_ok=True)
    os.makedirs(depth_out_dir, exist_ok=True)

    # ---- 0. (可选) 输出尺寸对齐:中心裁剪到目标宽高比 + 各向同性缩放 --------
    #  只在 --out_w/--out_h 都给了时启用;不启用时下面的逐帧循环与旧版逐字节一致。
    resize_cfg = None  # (crop_w, crop_h, off_x, off_y, scale, out_w, out_h)

    def _make_resize_cfg(w_in, h_in):
        ow, oh = args.out_w, args.out_h
        # 在原图内取与 ow:oh 同宽高比的最大中心矩形
        if w_in * oh >= h_in * ow:          # 原图相对更宽 -> 以高为准裁宽
            ch = h_in
            cw = int(round(h_in * ow / oh))
        else:                                # 原图相对更高 -> 以宽为准裁高
            cw = w_in
            ch = int(round(w_in * oh / ow))
        cw, ch = min(cw, w_in), min(ch, h_in)
        off_x = (w_in - cw) // 2
        off_y = (h_in - ch) // 2
        scale = ow / float(cw)               # 各向同性(oh/ch 在数值上等于它)
        return (cw, ch, off_x, off_y, scale, ow, oh)

    # ---- 1. 逐帧:读图/读深度/建 pose,写 image/cam/pfm --------------------
    Ks, Es, depths, cam_centers = [], [], [], []
    W = H = None
    for local_idx, fid in enumerate(frame_ids):
        img_glob = glob.glob(os.path.join(args.image_dir, f"{fid:06d}_lcam_front.png"))
        depth_glob = glob.glob(os.path.join(args.depth_dir, f"{fid:06d}_lcam_front_depth.png"))
        assert len(img_glob) == 1, (fid, img_glob)
        assert len(depth_glob) == 1, (fid, depth_glob)

        img = Image.open(img_glob[0]).convert("RGB")
        w_native, h_native = img.size
        assert w_native == h_native, f"预期方形原生图像, 实测 {w_native}x{h_native}"
        depth = decode_depth_png(depth_glob[0])
        assert depth.shape == (h_native, w_native), (depth.shape, h_native, w_native)

        # 原生分辨率下的内参:fov=90, 光心居中, 复刻 reader.py depth_to_dist()
        f_nat = w_native / 2.0
        K = np.array([[f_nat, 0, w_native / 2.0],
                      [0, f_nat, h_native / 2.0],
                      [0, 0, 1.0]], dtype=np.float64)

        if args.out_w and args.out_h:
            if resize_cfg is None:
                resize_cfg = _make_resize_cfg(w_native, h_native)
                print("[info] 尺寸对齐: %dx%d --crop--> %dx%d (off %d,%d) "
                      "--scale %.6f--> %dx%d" %
                      (w_native, h_native, resize_cfg[0], resize_cfg[1],
                       resize_cfg[2], resize_cfg[3], resize_cfg[4],
                       resize_cfg[5], resize_cfg[6]))
            cw, ch, ox, oy, s, ow, oh = resize_cfg
            img = img.crop((ox, oy, ox + cw, oy + ch)).resize((ow, oh), Image.BILINEAR)
            # 深度用最近邻,避免在深度不连续处插出并不存在的中间深度
            depth = cv2.resize(depth[oy:oy + ch, ox:ox + cw], (ow, oh),
                               interpolation=cv2.INTER_NEAREST)
            # 内参同步:先平移光心(裁剪),再整体缩放。深度值(米制 z)不受影响。
            K[0, 2] -= ox
            K[1, 2] -= oy
            K[:2, :] *= s

        if W is None:
            W, H = img.size
        assert img.size == (W, H), (img.size, W, H)
        assert depth.shape == (H, W), (depth.shape, H, W)

        SE_cv_c2w = ned_pose_to_cv_cam2world(poses[fid])
        E = np.linalg.inv(SE_cv_c2w)  # world-to-camera, 标准 CV 相机系

        Ks.append(K)
        Es.append(E)
        depths.append(depth)
        cam_centers.append(cam_center_from_E(E))

        img.save(os.path.join(img_out_dir, f"{local_idx:08d}.jpg"), quality=95)
        save_pfm(os.path.join(depth_out_dir, f"{local_idx:08d}.pfm"), depth.astype(np.float32))

    n = len(frame_ids)
    print(f"[info] 图像分辨率 = {W}x{H}, 共写出 {n} 帧 image/depth")

    # ---- 2. 逐帧写 cam.txt (extrinsic/intrinsic/depth_min depth_interval depth_num depth_max)
    for i in range(n):
        depth = depths[i]
        valid = depth[np.isfinite(depth) & (depth > 0) & (depth < 1000)]
        assert valid.size > 0, f"frame {i} 全部深度无效"
        zs_sorted = np.sort(valid)
        depth_min = float(zs_sorted[int(len(zs_sorted) * 0.01)])
        depth_max = float(zs_sorted[int(len(zs_sorted) * 0.99)])
        depth_num = args.depth_num_field
        depth_interval = (depth_max - depth_min) / max(depth_num - 1, 1)

        cam_path = os.path.join(cam_out_dir, f"{i:08d}_cam.txt")
        with open(cam_path, "w") as f_out:
            f_out.write("extrinsic\n")
            E = Es[i]
            for r in range(4):
                f_out.write(" ".join(str(E[r, c]) for c in range(4)) + " \n")
            f_out.write("\nintrinsic\n")
            K = Ks[i]
            for r in range(3):
                f_out.write(" ".join(str(K[r, c]) for c in range(3)) + " \n")
            f_out.write(f"\n{depth_min:.6f} {depth_interval:.6f} {depth_num} {depth_max:.6f} \n")

    # ---- 3. 计算共视分数矩阵(几何一致性反投影 + 官方角度高斯打分公式) --------
    print("[info] 计算共视分数矩阵(几何一致性 + 官方 view-selection score)...")
    rng = np.random.default_rng(0)
    score = np.zeros((n, n), dtype=np.float64)
    if args.pair_rule == "dvmvs":
        # deep-video-mvs keyframe_buffer.py get_best_measurement_frames 的罚分; 权重 1/(1+penalty) = tartanair_to_blend.write_pairs 同式
        sys.path.insert(0, "/root/ta2")
        from tartanair_to_blend import pose_distance, calculate_penalty
        c2w = [np.linalg.inv(E) for E in Es]
        for i in range(n):
            for j in range(n):
                if i != j:
                    _, R_m, t_m = pose_distance(c2w[i], c2w[j])
                    score[i, j] = 1.0 / (1.0 + calculate_penalty(t_m, R_m))
        print("[info] pair_rule=dvmvs: score=1/(1+penalty), %d x %d" % (n, n))
    for i in (range(n) if args.pair_rule != "dvmvs" else []):
        depth_i = depths[i]
        valid_i = depth_i[np.isfinite(depth_i) & (depth_i > 0) & (depth_i < 1000)]
        d_min_i, d_max_i = float(np.percentile(valid_i, 1)), float(np.percentile(valid_i, 99))
        for j in range(n):
            if j == i:
                continue
            mask = check_geometric_consistency(
                depth_i, Ks[i], Es[i], depths[j], Ks[j], Es[j], d_min_i, d_max_i)
            ys, xs = np.nonzero(mask)
            if len(xs) == 0:
                continue
            if args.score_grid > 0:
                g = ((ys % args.score_grid) == 0) & ((xs % args.score_grid) == 0)
                xs, ys = xs[g], ys[g]
            if args.score_grid <= 0 and len(xs) > args.score_sample_pixels:
                sel = rng.choice(len(xs), size=args.score_sample_pixels, replace=False)
                xs, ys = xs[sel], ys[sel]
            zs = depth_i[ys, xs]
            K_inv = np.linalg.inv(Ks[i])
            uv1 = np.stack([xs, ys, np.ones_like(xs)], axis=0).astype(np.float64)
            xyz_cam = K_inv @ (uv1 * zs[None, :])
            xyz_cam_h = np.vstack([xyz_cam, np.ones((1, xyz_cam.shape[1]))])
            cam2world_i = np.linalg.inv(Es[i])
            pts_world = (cam2world_i @ xyz_cam_h)[:3].T
            s = calc_score_from_points(cam_centers[i], cam_centers[j], pts_world)
            score[i, j] = s
        if i % 20 == 0:
            print(f"  ref {i}/{n} done")

    # ---- 4. 写 pair.txt (官方格式: "%d\n%d " + "id score id score ...") ------
    pair_path = os.path.join(cam_out_dir, "pair.txt")
    src_counts = []
    with open(pair_path, "w") as f_out:
        f_out.write(f"{n}\n")
        for i in range(n):
            order = np.argsort(-score[i])
            order = [k for k in order if score[i, k] > 0][:args.num_src]
            src_counts.append(len(order))
            f_out.write(f"{i}\n{len(order)} ")
            for k in order:
                f_out.write(f"{k} {score[i, k]:.6f} ")
            f_out.write("\n")
    print(f"[info] 写出 pair.txt: {pair_path}")
    # blend.py::build_list() 会丢弃 src 数 < nviews-1 的 ref(trainviews=9 -> 需要 >=8)
    print("[info] 每 ref 的 src 数: min=%d median=%d max=%d; "
          "src>=8 的 ref 数 = %d/%d" %
          (min(src_counts), int(np.median(src_counts)), max(src_counts),
           sum(1 for c in src_counts if c >= 8), n))

    nonzero_pairs = int((score > 0).sum())
    print(f"[info] 共视分数矩阵非零条目: {nonzero_pairs}/{n*n}, "
          f"平均每 ref 可用 src 数 = {nonzero_pairs / n:.2f}")

    # ---- 5. listfile ---------------------------------------------------------
    list_dir = os.path.join(args.out_root, "lists")
    os.makedirs(list_dir, exist_ok=True)
    list_path = os.path.join(list_dir, "train.txt")
    with open(list_path, "w") as f_out:
        f_out.write(args.scan_name + "\n")
    print(f"[info] 写出 listfile: {list_path}")

    meta = {
        "scan_name": args.scan_name,
        "n_frames": n,
        "frame_ids_in_traj": frame_ids,
        "resolution": [W, H],
        "intrinsics_fx_fy_cx_cy": [float(Ks[0][0, 0]), float(Ks[0][1, 1]),
                                    float(Ks[0][0, 2]), float(Ks[0][1, 2])],
        "resize_cfg_crop_w_h_offx_offy_scale_outw_outh": resize_cfg,
        "num_src_requested": args.num_src,
        "min_src_per_ref": int(min(src_counts)) if src_counts else 0,
        "nonzero_pairs": nonzero_pairs,
    }
    with open(os.path.join(scan_dir, "conversion_meta.json"), "w") as f_out:
        json.dump(meta, f_out, indent=2)
    print("[done]")


if __name__ == "__main__":
    main()
