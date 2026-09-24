#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
infinigen_to_blend.py  —— Infinigen (Indoors) 渲染输出 -> CasDiffMVS 训练用 blend 目录格式

目标布局 (datasets/blend.py 的 MVSDataset 原样能读):
    {out}/ig_{scan}/blended_images/{:08d}.jpg
    {out}/ig_{scan}/cams/{:08d}_cam.txt
    {out}/ig_{scan}/cams/pair.txt
    {out}/ig_{scan}/rendered_depth_maps/{:08d}.pfm

================================================================================
铁律: 不自研。下面逐项列出【抄自哪个文件的哪一段】, 以及每一处偏离与理由。
================================================================================

== A. 目标侧 (CasDiffMVS) ==
A1 cam.txt 版式与语义
   /root/diffmvs_full/datasets/blend.py:51-62  read_cam_file() (depth 行 :59-60)
     lines[1:5]  = extrinsic 4x4 = cam_T_world (world->camera)
     lines[7:10] = intrinsic 3x3
     lines[11]   -> depth_min = split()[0], depth_max = split()[-1]
   /root/diffmvs_full/datasets/blend.py:135-140  mask_ms
     mask = (depth >= depth_min) & (depth <= depth_max)
     🔴 也就是说第 12 行【直接决定哪些像素进 loss】。
A2 三个子目录名 + pair.txt 在 cams/ 下, 不在 scan 根
   /root/diffmvs_full/datasets/blend.py:34, :94-105
A3 extrinsic = cam_T_world 的交叉印证
   /root/old_box_archive/mvsa_fork/src/mvsanywhere/datasets/infinigen_cubism.py:390-397
     "cam_T_world = extrinsics; world_T_cam = inv(cam_T_world)"
A4 pfm 用官方 datasets/data_io.py::save_pfm (与 tartanground2mvsnet.py / sp2mvsnet.py 同一份)

== B. 源侧 (Infinigen) —— 100% 抄官方自己的 MVS 导出脚本 ==
B1 目录布局 frames/{Image,camview,Depth}/camera_{subcam}/
   /root/infinigen/src/infinigen/tools/process_mvs_data.py:124-155  (官方 MVS 导出)
   非重整布局(渲染中途报错时文件是平铺的)也支持: 本脚本递归搜。
B2 camview_*.npz = {K(3,3), T(4,4), HW(2,)}
   写出点: /root/infinigen/src/infinigen/core/placement/camera.py:834-864 (T 在 :861-863)
     T = np.asarray(camera_obj.matrix_world) @ np.diag((1,-1,-1,1))   # 注释原文 "Y down Z forward (aka opencv)"
     HW = (resolution_y, resolution_x)
   C++ 侧同样注释: /root/infinigen/src/infinigen/datagen/customgt/src/camera_view.cpp:76
   => T 是 camera-to-world, OpenCV 相机系 (x 右 y 下 z 前)。 extrinsic = inv(T)。
B3 深度是【平面 Z】(沿光轴), 不是射线距离 —— 官方两处反投影代码逐字为证:
   /root/infinigen/src/infinigen/tools/process_mvs_data.py:39-48  reproject()
   /root/infinigen/src/infinigen/tools/ground_truth/rigid_warp.py:42-50  reproject()
     cam1_coords = einsum(depth1, [x,y,1], inv(K1))    <- 深度直接乘齐次射线 = 平面 Z
     rel_pose    = inv(pose2) @ pose1                  <- pose 就是 camview["T"] (c2w)
   本脚本的自证 (--selfcheck) 会同时给出【当成射线距离】的残差, 两者一比即可证伪。
B4 深度分辨率与图像不同时怎么办 (opengl_gt 的 Depth 是 2H x 2W):
   /root/infinigen/src/infinigen/tools/ground_truth/rigid_warp.py:75-77
     depth1 = cv2.resize(np.load(depth_path), dsize=(W,H), interpolation=cv2.INTER_LINEAR)
   2x 的来源: /root/infinigen/src/infinigen/datagen/customgt/main.cpp:204-205 buffer=output*2
              /root/infinigen/src/infinigen/datagen/customgt/src/camera_view.cpp:91-93 K 也整体 *2
   blender_gt 路径的 Depth 是 1x (render.py:361-367 直接存 EXR Z pass 再转 npy), 不触发 resize。
B5 黑帧过滤 im.mean() < 20
   /root/infinigen/src/infinigen/tools/process_mvs_data.py:130
B6 文件名后缀解析 parse_suffix (cam_rig/resample/frame/subcam)
   /root/infinigen/src/infinigen/tools/suffixes.py  —— 按文件路径直接 import, 逐字使用, 不重写
B7 官方自己的共视分数 (供对照, 见 --score_rule infinigen_cov)
   /root/infinigen/src/infinigen/tools/process_mvs_data.py:39-107 (reproject/induced_flow/check_cycle_consistency/compute_covisibility)
     前后向诱导光流 + 循环一致性 (阈值 1 px) 的像素占比

== C. 视角选择 (pair.txt) —— 照抄 MVSNet 官方 ==
C1 calc_score: /root/colmap2mvsnet_np2.py:280-302
     score = 共视点计数;  若共视点三角化角的 75 分位 < 1 度 -> score = 0
C2 num_view = min(20, len(images)-1):  /root/colmap2mvsnet_np2.py:405-412
     🔴 必须 20 不是 10 —— 09-22 我们因为只给 10 个 src 吃过大亏
       (colmap2mvsnet_np2.py:418 写死 20; 融合遍历全部 src 不截断)
C3 pair.txt 写法: /root/colmap2mvsnet_np2.py:442-449
     "%d\n" % N ;  每 ref: "%d\n%d " % (i, len(sel)) + "id score " ...
C4 用【GT 深度反投影 + 官方 filter.py 几何一致性】代替 COLMAP 稀疏点交集来得到共视点集:
     这一替换【不是我发明的】, 逐字抄自同仓已有的
     /root/tartanground2mvsnet.py:130-200  (reproject_with_depth / check_geometric_consistency
     / calc_score_from_points), 该文件头已标明其出处是官方 filter.py:8-104,
     阈值 geo_pixel_thres=1.0 / geo_depth_thres=0.01 也是官方默认。

== D. 深度范围 (cam.txt 第 12 行) ==
D1 p1 / p99: /root/colmap2mvsnet_np2.py:378-381 的 zs_sorted[int(len*.01)] / [int(len*.99)]
   同仓两处已在用同一条: /root/ta2/tartanair_to_blend.py::frame_range,
                         /root/sp2mvsnet.py::depth_range
D2 depth_interval / depth_num 字段: colmap2mvsnet_np2.py:400-401, depth_num 默认 192
   (blend.py 只读该行首尾两个 token, 中间两个仅为兼容; 与 sp2mvsnet.py / tartanground2mvsnet.py 一致)
D3 深度有效性 (d>0) & (d<1e3):
   /root/old_box_archive/mvsa_fork/src/mvsanywhere/datasets/infinigen_cubism.py:337,366
   /root/sp2mvsnet.py:31  SENTINEL_HI=1e3

================================================================================
偏离清单 (Deviations)
================================================================================
DEV-1  官方 colmap2mvsnet_np2.py:380-381 对 p1/p99 还乘了 0.75 / 1.25 放宽。本脚本【不放宽】。
       理由: blend.py:135-140 把 [depth_min, depth_max] 直接当 loss mask 用, 放宽=把更多
       (很可能是背景/无效)像素纳入监督。TartanAir 域刚因为 depth_max 被天空撑到 65504 吃过亏
       (MEMORY: 44.38% 的 cam 文件被撑大)。同仓 tartanair_to_blend.py / sp2mvsnet.py 两个
       转换器也都【不放宽】, 本脚本与它们保持一致。--relax_range 可打开官方放宽以做对照。
DEV-2  官方 process_mvs_data.py 用 cam_rig 当视角索引 (:149 cam_id = parse_suffix(image)["cam_rig"]),
       因为官方 MVS 配方是 30 个静止 camera_rig 单帧 (docs/source/ConfiguringCameras.md:99)。
       本脚本按 (cam_rig, frame) 字典序统一编号, 这样【多机位单帧】和【单机位多帧(视频)】两种
       产物都能转。单机位多帧时退化为按 frame 排序, 与官方索引一致。
DEV-3  深度重采样默认用官方 rigid_warp.py 的 cv2.INTER_LINEAR。但 INTER_LINEAR 会在深度不连续处
       插出并不存在的中间深度 (同仓 tartanground2mvsnet.py:329-330 因此用 INTER_NEAREST)。
       提供 --depth_resize nearest 切换。blender_gt 路径深度本来就是 1x, 该分支不触发。
DEV-4  16:9 -> 4:3 的裁剪 (--crop_aspect): 官方【没有】这段代码, 官方做法是一开始就按目标
       分辨率生成 (execute_tasks.generate_resolution, execute_tasks.py:235)。
       裁剪 + 内参改动逐字抄同仓 /root/ta2/tartanair_to_blend.py:154-158 与
       /root/tartanground2mvsnet.py:330-338: 先在原图内取与目标宽高比相同的最大中心矩形,
       K[0,2]-=off_x, K[1,2]-=off_y, 再各向同性缩放 K[:2,:]*=s。
       ⚠ 数学等价性 (见文末"4:3 结论"): 16:9 渲染后横向中心裁到 4:3, 与原生 4:3 渲染得到的
       K 完全一致(fx,fy,cy 不变, cx 减去偏移), 因为 adjust_camera_sensor 固定 sensor_height=18,
       焦距(mm)不随宽高比变 => fy 只由 H 决定。所以裁剪是【无损且内参可精确改写】的。
DEV-5  JPEG quality 95 (与 tartanair_to_blend.py:198 / tartanground2mvsnet.py:349 / sp2mvsnet.py:24 一致)
DEV-6  pair.txt 的分数字段: 官方 colmap2mvsnet_np2.py:447 写 '%d'(整数)。计数型分数无损, 故默认照抄;
       --score_rule infinigen_cov 时分数是 [0,1] 浮点, 写 '%.6f' (否则全变 0)。
DEV-7  Infinigen 室内 terrain_enabled=False 没有天空, 所以不需要 TartanAir 的天空掩码。
       但 Blender Z pass 在没有几何的方向会给极大值, 仍用 D3 的 (d>0)&(d<1e3) 挡住,
       并且 --selfcheck 会把每帧 depth_max 打出来, 被撑大就看得见。
DEV-8  本脚本【不写】{out}/lists/*.txt。/root/monotrain/lists/ 下的 full / full_v3 等是共享
       清单, 训练在读; 本脚本只负责产出一个 scan 目录, 清单由上层脚本合并。
       (tartanground2mvsnet.py:455-461 会写 lists/train.txt, 这里刻意不抄那一段。)
DEV-9  官方 colmap2mvsnet_np2.py:405-412 取 top-20 时【不过滤 score==0】。本脚本默认照抄,
       但会把零分 src 的条数打印出来告警: blend.py 训练模式是
       random.sample(src_views, nviews-1) (blend.py:80), 零分 src 会被等概率抽中,
       等于拿一对没有共视的图去算 loss。--drop_zero_score 可切换成
       tartanground2mvsnet.py:433 的过滤做法 (代价是某些 ref 的 src 数掉到 7 以下被 blend.py 丢掉)。

================================================================================
实测 (2026-09-23, 箱上真跑, 见报告)
================================================================================
数据来源: /root/igmv (本仓 /root/igmv.sh 生成)
  官方 MVS 室内配方 docs/source/ConfiguringCameras.md:99, n_camera_rigs 30->12,
  原生 768x576 (execute_tasks.generate_resolution), blender_gt 拿 Depth, 纯 CPU。
转换命令:
  python /root/infinigen_to_blend.py --frames /root/igmv/frames \
      --scan seed0_dining --out /root/monotrain
结果 (/root/monotrain/ig_seed0_dining, 12 视角, 768x576):
  K = [[480,0,384],[0,480,288]]   (与 aspect_probe 预测的原生 4:3 内参逐位一致)
  重投影中位残差 (平面 Z)          = 0.0300 px      <- 判据
  重投影中位残差 (当成射线距离)    = 7.8610 px      <- 深度语义的阴性对照, 差 262 倍
  几何一致像素占比                 = 0.7269         (其余是遮挡/出界, 真实几何本就如此)
  depth_min 1.048~1.389 m / depth_max 2.993~5.274 m (没有被背景撑大)
  进 loss 的像素占比               = 0.9800
  每 ref 的 src 数                 = 11 (= min(20, 12-1)), 零分 src 0 条
  训练 dataloader (datasets/blend.py, trainviews=8) 实读: metas = 12, mask 占比 0.9800
阴性对照 (同一份数据, 只改一处):
  --negative_control transpose_R   -> 176.49 px (5900x), 一致像素 0.0020, 零分 src 51 条
  --negative_control flip_t        -> 697.44 px (23000x), 一致像素 0.0004, 零分 src 74 条
  --negative_control shuffle_depth -> 30.16 px (1000x), 一致像素 0.0122
     🔴 但注意: 这一档下 pair.txt 的【每 ref 非零分 src 数仍然是 11】—— 因为 np2 的
     calc_score 是【共视点计数】, 哪怕只剩 1.2% 的一致像素也还有上万个点, 计数照样非零。
     => pair.txt 的分数对"深度与相机配错"这个失效模式【不报警】, 只有重投影残差报警。
        这就是为什么本脚本把 selfcheck 默认打开而不是只看 pair 统计。
合成对照 (/root/ig_synth_test.py, 解析求交的长方体房间, 几何精确已知):
  正确        0.00047 px  |  transpose_R 456.24 px  |  flip_t 1607.00 px
  16:9(1280x720) 裁+缩到 768x576 后 K 与原生 4:3 逐位相同, 残差 0.0096 px

================================================================================
坐标系约定 (一句话)
================================================================================
camview["T"] = camera-to-world, OpenCV 相机系 (x 右, y 下, z 前), 单位米。
cam.txt 的 extrinsic = inv(T) = world-to-camera。
深度 = 沿相机 z 轴的平面深度(米), 与 K 配对反投: X_cam = inv(K) @ [u,v,1] * d。

================================================================================
4:3 结论 (实测, 见 /root/aspect_probe.py 的输出)
================================================================================
(a) 报错影响什么: render.py:553-555 先把分辨率改成 override 值, 然后 bpy.ops.render.render()
    【渲染照常完成】, 再进 "Post Processing" 调 save_camera_parameters ->
    get_calibration_matrix_K_from_blender 抛 ValueError (util/camera.py:24-37, raise 在 :35)。
    后果 = 出了 Image_*.png/exr, 但【camview_*.npz 没写出】, 并且它后面的
    postprocess / reorganize_old_framesfolder 全部没跑(文件平铺在 frames 根)。
    实证: /root/igr_r0768x576.log:878 就是这条 ValueError(sensor 32x18 vs 768x576);
          /root/igr/r0768x576/ 有 Image 无 camview, 且是平铺布局。
    => 没有相机参数 = 这批 4:3 渲染产物【一张都不能变成训练数据】(本脚本对
       /root/ig_probe/frames 跑一遍就会打印 "drop ...: no Depth / no camview")。
(b) adjust_camera_sensor 本身【并不排斥 4:3】: sensor_width = 18*(W/H),
    4:3 得 24.0 整除通过, 16:9 得 32.0 通过; 真正过不去的是 1366x768 这种 (32.015625)。
    报错的真实成因是【相机 sensor 是在 coarse 期 spawn_camera 时按当时分辨率定死的】,
    渲染期只改 scene.render.resolution 不改 sensor。
    官方正解两条, 都实测通过:
      1. 一开始就按目标分辨率生成: -p execute_tasks.generate_resolution=(768,576)
         (execute_tasks.py:235 在 spawn_camera 之前执行) —— 本仓 /root/igmv 就是这么生成的,
         coarse rc=0, camview 里 K = [[480,0,384],[0,480,288],[0,0,1]]。
         同时建议跟上 get_sensor_coords.W/H (base.gin:64-65 默认 1280/720)。
      2. 改完分辨率立刻调 adjust_camera_sensor —— 这正是 infinigen2 官方渲染器的顺序:
         infinigen2/exporters/render_cycles.py:338-346。
(c) 万一只有 16:9 的产物, 裁成 4:3 时内参怎么改 (--out_w/--out_h 已实现, DEV-4):
    因为 adjust_camera_sensor 把 sensor_height 恒定为 18mm, 焦距(mm)与宽高比无关,
    所以 fy_px = f_mm * H / 18 【只由 H 决定】; 横向裁剪不改 fx/fy/cy, 只改 cx。
      K_4:3 = K_16:9, 但 cx -= (W16 - W43)//2 ,  W43 = round(H * 4/3)
    实测 (aspect_probe.py): 1280x720 K=[[600,0,640],[0,600,360]] ,
      裁到 960x720 -> cx 640-160=480 , 与【原生渲 960x720】的 K 逐位相同, 最大绝对差 0.0;
      再各向同性缩放 0.8 到 768x576 -> [[480,0,384],[0,480,288]] , 与【原生渲 768x576】
      的 K 最大绝对差 0.0。
    => 16:9 渲完裁 4:3 在内参上是【精确无损】的, 只损失横向视场。
"""

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import defaultdict

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# 官方 pfm 写出 (与训练 dataloader 逐字节同源)
DIFFMVS_DIR = os.environ.get("DIFFMVS_DIR", "/root/diffmvs_full")
sys.path.insert(0, DIFFMVS_DIR)
from datasets.data_io import save_pfm  # noqa: E402

# 官方 parse_suffix —— 按文件路径 import, 避免触发 infinigen 包 __init__ (它要 bpy)
_SUFFIX_PY = os.environ.get(
    "INFINIGEN_SUFFIXES_PY", "/root/infinigen/src/infinigen/tools/suffixes.py"
)
_spec = importlib.util.spec_from_file_location("ig_suffixes", _SUFFIX_PY)
_ig_suffixes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ig_suffixes)
parse_suffix = _ig_suffixes.parse_suffix  # infinigen/tools/suffixes.py:31-49

# ---------------------------------------------------------------------------
# 官方常量
SENTINEL_HI = 1e3        # infinigen_cubism.py:337 / sp2mvsnet.py:31
BLACK_FRAME_MEAN = 20    # process_mvs_data.py:130
GEO_PIXEL_THRES = 1.0    # filter.py:73  (经 tartanground2mvsnet.py:80-81 转录)
GEO_DEPTH_THRES = 0.01   # filter.py:74
JPEG_Q = 95
DEPTH_NUM_FIELD = 192    # colmap2mvsnet_np2.py argparse --max_d 默认


# ===========================================================================
# 1. 读 Infinigen 产物
# ===========================================================================
def _index_frames(frames_root, subcam):
    """递归收集 Image/Depth/camview 三件套, 按 parse_suffix 的 key 对齐。

    同时支持官方重整后的 frames/<Pass>/camera_<subcam>/<Pass>_<suffix>.<ext>
    (process_mvs_data.py:124-141) 和渲染中途报错时的平铺布局。

    🔴 同一个 suffix 可能同时存在两份:
       - 官方重整后的  <frames>/<Pass>/camera_<subcam>/<Pass>_<suffix>.<ext>
       - 平铺的        <frames>/<Pass>_<suffix>.<ext>
       后者是【渲染后报错导致 reorganize_old_framesfolder 没跑完】留下的残骸
       (实测 /root/ig_probe/frames 下就同时有 1280x720 的重整版和 768x576 的平铺残骸)。
       规则: 重整路径优先, 并把冲突打出来 —— 否则会拿到分辨率都对不上的错文件。
    """
    buckets = defaultdict(dict)
    conflicts = []
    for dirpath, _dirnames, filenames in os.walk(frames_root):
        for fn in filenames:
            m = re.match(r"^(Image|Depth|camview)_(.+)\.(png|exr|npy|npz)$", fn)
            if not m:
                continue
            kind, ext = m.group(1), m.group(3)
            idx = parse_suffix(fn)
            if idx is None or idx["subcam"] != subcam:
                continue
            key = (idx["cam_rig"], idx["resample"], idx["frame"], idx["subcam"])
            slot = f"{kind}_{ext}"
            path = os.path.join(dirpath, fn)
            # 是否处在官方重整布局 <Pass>/camera_<subcam>/ 下
            canonical = (os.path.basename(dirpath) == f"camera_{subcam}" and
                         os.path.basename(os.path.dirname(dirpath)) == kind)
            prev = buckets[key].get(slot)
            if prev is None:
                buckets[key][slot] = path
                buckets[key][slot + "_canon"] = canonical
            else:
                conflicts.append((slot, key, prev, path))
                if canonical and not buckets[key].get(slot + "_canon"):
                    buckets[key][slot] = path
                    buckets[key][slot + "_canon"] = True
            buckets[key]["_idx"] = idx
    for slot, key, p1, p2 in conflicts[:10]:
        print(f"[warn] {slot} {key} 同 suffix 有多份, 取重整布局那份: {p1} | {p2}")
    return buckets


def _load_depth_raw(paths):
    """Depth_npy (blender_gt 的 postprocess 存的 / customgt 存的) 优先, 退回 Depth_exr。"""
    if "Depth_npy" in paths:
        return np.load(paths["Depth_npy"]).astype(np.float32), paths["Depth_npy"]
    if "Depth_exr" in paths:
        # render.py:361-367 的 Depth EXR 单通道; 正常情况它会被 postprocess 转成 npy 后删掉
        d = cv2.imread(paths["Depth_exr"], cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
        if d is None:
            return None, None
        if d.ndim == 3:
            d = d[..., 0]
        return d.astype(np.float32), paths["Depth_exr"]
    return None, None


def load_views(frames_root, subcam, depth_resize, skip_black):
    """-> list of dict(key, K, T_c2w, img(BGR), depth(HxW float32))  按 key 排序"""
    buckets = _index_frames(frames_root, subcam)
    views, dropped = [], []
    for key in sorted(buckets):
        p = buckets[key]
        if "camview_npz" not in p:
            dropped.append((key, "no camview")); continue
        if "Image_png" not in p and "Image_exr" not in p:
            dropped.append((key, "no Image")); continue
        cv_npz = np.load(p["camview_npz"])
        K = np.asarray(cv_npz["K"], dtype=np.float64)
        T = np.asarray(cv_npz["T"], dtype=np.float64)     # camera.py:860-862 c2w OpenCV
        HW = np.asarray(cv_npz["HW"]).astype(int)
        H, W = int(HW[0]), int(HW[1])

        img_path = p.get("Image_png") or p["Image_exr"]
        img = cv2.imread(img_path, cv2.IMREAD_COLOR)
        if img is None:
            dropped.append((key, "Image unreadable")); continue
        if img.shape[:2] != (H, W):
            dropped.append((key, f"Image {img.shape[:2]} != camview HW {(H,W)}")); continue
        if skip_black and img.mean() < BLACK_FRAME_MEAN:   # process_mvs_data.py:130
            dropped.append((key, f"black frame mean={img.mean():.1f}")); continue

        d, dpath = _load_depth_raw(p)
        if d is None:
            dropped.append((key, "no Depth")); continue
        d_native_shape = d.shape
        if d.shape != (H, W):
            # rigid_warp.py:78-80 —— 官方就是 cv2.resize 到图像分辨率
            interp = cv2.INTER_LINEAR if depth_resize == "linear" else cv2.INTER_NEAREST
            d = cv2.resize(d, dsize=(W, H), interpolation=interp)
        d = np.ascontiguousarray(d.astype(np.float32))
        d[~np.isfinite(d)] = 0.0

        views.append(dict(key=key, K=K, T=T, img=img, depth=d, H=H, W=W,
                          img_path=img_path, depth_path=dpath,
                          depth_native_shape=tuple(d_native_shape)))
    return views, dropped


# ===========================================================================
# 2. 裁剪 / 缩放 (DEV-4; 抄 tartanground2mvsnet.py:_make_resize_cfg + :330-338)
# ===========================================================================
def make_resize_cfg(w_in, h_in, ow, oh):
    if w_in * oh >= h_in * ow:          # 原图相对更宽 -> 以高为准裁宽
        ch = h_in
        cw = int(round(h_in * ow / oh))
    else:
        cw = w_in
        ch = int(round(w_in * oh / ow))
    cw, ch = min(cw, w_in), min(ch, h_in)
    return (cw, ch, (w_in - cw) // 2, (h_in - ch) // 2, ow / float(cw), ow, oh)


def apply_resize(view, cfg, depth_resize):
    cw, ch, ox, oy, s, ow, oh = cfg
    img = view["img"][oy:oy + ch, ox:ox + cw]
    img = cv2.resize(img, (ow, oh), interpolation=cv2.INTER_AREA)
    interp = cv2.INTER_LINEAR if depth_resize == "linear" else cv2.INTER_NEAREST
    dep = cv2.resize(view["depth"][oy:oy + ch, ox:ox + cw], (ow, oh), interpolation=interp)
    K = view["K"].copy()
    K[0, 2] -= ox
    K[1, 2] -= oy
    K[:2, :] *= s
    view.update(img=img, depth=np.ascontiguousarray(dep.astype(np.float32)),
                K=K, H=oh, W=ow)
    return view


# ===========================================================================
# 3. 深度范围 (D1/D2, DEV-1)
# ===========================================================================
def valid_mask(d, max_depth=SENTINEL_HI):
    return np.isfinite(d) & (d > 0) & (d < max_depth)


def depth_range(d, max_depth=SENTINEL_HI, relax=False):
    zs = np.sort(d[valid_mask(d, max_depth)].astype(np.float64).ravel())
    if zs.size < 100:
        return None
    dmin = float(zs[int(len(zs) * .01)])
    dmax = float(zs[int(len(zs) * .99)])
    if relax:                           # colmap2mvsnet_np2.py:380-381
        dmin, dmax = dmin * 0.75, dmax * 1.25
    return dmin, dmax


# ===========================================================================
# 4. 官方几何一致性 (逐字抄 /root/tartanground2mvsnet.py:130-180 = 官方 filter.py:8-104)
# ===========================================================================
def reproject_with_depth(depth_ref, K_ref, E_ref, depth_src, K_src, E_src):
    width, height = depth_ref.shape[1], depth_ref.shape[0]
    x_ref, y_ref = np.meshgrid(np.arange(0, width), np.arange(0, height))
    x_ref, y_ref = x_ref.reshape([-1]), y_ref.reshape([-1])
    xyz_ref = np.matmul(
        np.linalg.inv(K_ref),
        np.vstack((x_ref, y_ref, np.ones_like(x_ref))) * depth_ref.reshape([-1]))
    xyz_src = np.matmul(np.matmul(E_src, np.linalg.inv(E_ref)),
                        np.vstack((xyz_ref, np.ones_like(x_ref))))[:3]
    K_xyz_src = np.matmul(K_src, xyz_src)
    xy_src = K_xyz_src[:2] / K_xyz_src[2:3]
    x_src = xy_src[0].reshape([height, width]).astype(np.float32)
    y_src = xy_src[1].reshape([height, width]).astype(np.float32)
    sampled_depth_src = cv2.remap(depth_src, x_src, y_src, interpolation=cv2.INTER_LINEAR)

    xyz_src2 = np.matmul(
        np.linalg.inv(K_src),
        np.vstack((xy_src, np.ones_like(x_ref))) * sampled_depth_src.reshape([-1]))
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
    return mask, dist, relative_depth_diff


def cam_center_from_E(E):
    return -E[:3, :3].T @ E[:3, 3]


# ===========================================================================
# 5. 视角选择分数
# ===========================================================================
def calc_score_mvsnet(cam_center_i, cam_center_j, pts_world):
    """逐字复刻 /root/colmap2mvsnet_np2.py:280-302 calc_score 的打分逻辑:
       score = 共视点【计数】; 若三角化角 75 分位 < 1 度 -> score = 0。
       (np2 里高斯那行是注释掉的, 所以这里也不用高斯 —— 与 np2 逐字一致)"""
    n = len(pts_world)
    if n == 0:
        return 0.0
    vi = cam_center_i[None, :] - pts_world
    vj = cam_center_j[None, :] - pts_world
    den = np.maximum(np.linalg.norm(vi, axis=1) * np.linalg.norm(vj, axis=1), 1e-12)
    theta = np.degrees(np.arccos(np.clip(np.sum(vi * vj, axis=1) / den, -1.0, 1.0)))
    ang = np.sort(theta)
    if ang[int(len(ang) * 0.75)] < 1:      # colmap2mvsnet_np2.py:299-301
        return 0.0
    return float(n)


# --- 官方 Infinigen 自己的共视分数 (B7), 仅作对照 -------------------------
def _ig_transform(T, p):                       # process_mvs_data.py:24-26
    return np.einsum("H W j, i j -> H W i", p, T[:3, :3]) + T[:3, 3]


def _ig_from_homog(x):                         # process_mvs_data.py:29-30
    return x[..., :-1] / x[..., [-1]]


def ig_reproject(depth1, pose1, pose2, K1, K2):   # process_mvs_data.py:39-48
    H, W = depth1.shape
    x, y = np.meshgrid(np.arange(W), np.arange(H), indexing="xy")
    img_1_coords = np.stack((x, y, np.ones_like(x)), axis=-1).astype(np.float64)
    cam1_coords = np.einsum("H W, H W j, i j -> H W i", depth1, img_1_coords,
                            np.linalg.inv(K1))
    rel_pose = np.linalg.inv(pose2) @ pose1
    cam2_coords = _ig_transform(rel_pose, cam1_coords)
    return _ig_from_homog(np.einsum("H W j, i j -> H W i", cam2_coords, K2))


def ig_covisibility(d0, d1, K0, K1, T0, T1):
    """process_mvs_data.py:85-107 的 numpy 等价实现 (原版用 torch.grid_sample 做双线性采样,
       这里用 cv2.remap 双线性, 数值等价; 不引 torch 依赖)。阈值 1 px 照抄。"""
    H, W = d0.shape
    c1 = ig_reproject(d0, T0, T1, K0, K1)
    x, y = np.meshgrid(np.arange(W), np.arange(H), indexing="xy")
    flow01 = c1 - np.stack([x, y], axis=-1)
    H1, W1 = d1.shape
    c0 = ig_reproject(d1, T1, T0, K1, K0)
    x1, y1 = np.meshgrid(np.arange(W1), np.arange(H1), indexing="xy")
    flow10 = c0 - np.stack([x1, y1], axis=-1)
    coords1 = np.stack([x, y], axis=-1) + flow01
    f10x = cv2.remap(flow10[..., 0].astype(np.float32),
                     coords1[..., 0].astype(np.float32),
                     coords1[..., 1].astype(np.float32), cv2.INTER_LINEAR)
    f10y = cv2.remap(flow10[..., 1].astype(np.float32),
                     coords1[..., 0].astype(np.float32),
                     coords1[..., 1].astype(np.float32), cv2.INTER_LINEAR)
    cycle = np.sqrt((f10x + flow01[..., 0]) ** 2 + (f10y + flow01[..., 1]) ** 2)
    return float((cycle < 1).mean())


# ===========================================================================
# 6. 自证 (判据)
# ===========================================================================
def selfcheck(views, Es, n_pairs=8, grid=8, depth_as_ray=False):
    """把深度反投影成 3D 点 -> 投到另一个视图 -> 用那边的深度再投回来, 量残差。

    抄 /root/ta2/tartanair_to_blend.py:57-79 cross_view_check 的思路, 但判据换成
    官方 filter.py 的两个量 (dist 像素, relative_depth_diff), 因为这两个量【同时】
    能抓外参错、内参错、深度语义错(平面 Z vs 射线距离):
      - 外参转置/取反  -> dist 爆到几十~几百 px
      - 平面 Z 当射线距离 -> 视场边缘 dist 系统性偏, 中位仍 > 1 px
    返回 (median_dist_px, median_rel_depth_diff, frac_consistent)
    """
    res_d, res_z, res_f = [], [], []
    n = len(views)
    for i in range(0, n, max(1, n // n_pairs))[:n_pairs]:
        j = (i + 1) % n
        if j == i:
            continue
        di, dj = views[i]["depth"].copy(), views[j]["depth"].copy()
        Ki, Kj = views[i]["K"], views[j]["K"]
        if depth_as_ray:
            # 阴性对照用: 若深度其实是射线距离, 应当先除以 |ray| 才是平面 Z
            for d, K in ((di, Ki), (dj, Kj)):
                H, W = d.shape
                x, y = np.meshgrid(np.arange(W), np.arange(H))
                r = np.stack([(x - K[0, 2]) / K[0, 0], (y - K[1, 2]) / K[1, 1],
                              np.ones_like(x, dtype=np.float64)])
                d /= np.linalg.norm(r, axis=0).astype(np.float32)
        rng = depth_range(di)
        if rng is None:
            continue
        mask, dist, rel = check_geometric_consistency(di, Ki, Es[i], dj, Kj, Es[j],
                                                      rng[0], rng[1])
        vm = valid_mask(di)[::grid, ::grid]
        dd = dist[::grid, ::grid][vm]
        rr = rel[::grid, ::grid][vm]
        if dd.size < 50:
            continue
        res_d.append(float(np.median(dd)))
        res_z.append(float(np.median(rr)))
        res_f.append(float(mask[::grid, ::grid][vm].mean()))
    if not res_d:
        return float("inf"), float("inf"), 0.0
    return float(np.median(res_d)), float(np.median(res_z)), float(np.median(res_f))


# ===========================================================================
# 7. 主流程
# ===========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", required=True,
                    help="Infinigen 的 frames 目录 (含 Image/Depth/camview, 或平铺产物)")
    ap.add_argument("--out", default="/root/monotrain")
    ap.add_argument("--scan", required=True, help="场景名, 最终目录是 {out}/ig_{scan}")
    ap.add_argument("--subcam", type=int, default=0)
    ap.add_argument("--out_w", type=int, default=0, help="0 = 保持原生分辨率")
    ap.add_argument("--out_h", type=int, default=0)
    ap.add_argument("--depth_resize", choices=["linear", "nearest"], default="linear",
                    help="linear = 官方 rigid_warp.py:75-77; nearest 见 DEV-3")
    ap.add_argument("--max_depth", type=float, default=SENTINEL_HI)
    ap.add_argument("--relax_range", action="store_true",
                    help="打开 colmap2mvsnet_np2.py:380-381 的 *0.75/*1.25 放宽 (见 DEV-1)")
    ap.add_argument("--score_rule", choices=["mvsnet_count", "infinigen_cov"],
                    default="mvsnet_count")
    ap.add_argument("--score_grid", type=int, default=8,
                    help="共视点采样步长 (8 = CasDiffMVS stage1 的 1/8 分辨率, blend.py:120-126 的 stage1 = 1/8)")
    ap.add_argument("--num_view", type=int, default=20,
                    help="pair.txt 每 ref 的 src 数上限; 官方 colmap2mvsnet_np2.py:418 = 20")
    ap.add_argument("--min_frames", type=int, default=8)
    ap.add_argument("--no_skip_black", action="store_true")
    ap.add_argument("--drop_zero_score", action="store_true",
                    help="把 pair.txt 里分数=0 的 src 丢掉 (见 DEV-9)。默认关 = 与官方 np2:405-412 逐字一致")
    ap.add_argument("--selfcheck", action="store_true", default=True)
    ap.add_argument("--negative_control",
                    choices=["none", "transpose_R", "flip_t", "shuffle_depth"],
                    default="none",
                    help="阴性对照: 故意把外参/深度配错, 自证必须报警。"
                         "shuffle_depth = 把第 i 个视角的深度换成第 i+1 个的, 专门验"
                         "【camview / Depth / Image 三者按后缀对齐】这段索引逻辑")
    ap.add_argument("--dry_run", action="store_true", help="只自证, 不落盘")
    a = ap.parse_args()

    views, dropped = load_views(a.frames, a.subcam, a.depth_resize,
                                skip_black=not a.no_skip_black)
    print(f"[info] 收到 {len(views)} 个视角, 丢弃 {len(dropped)}")
    for k, why in dropped[:20]:
        print(f"   drop {k}: {why}")
    if len(views) < a.min_frames:
        print(f"[FATAL] 有效视角 {len(views)} < min_frames {a.min_frames} "
              f"—— blend.py:41-43 会把 src 数不足的 ref 全丢掉, 产不出可训练样本")
        sys.exit(3)

    print(f"[info] 原生分辨率 = {views[0]['W']}x{views[0]['H']}, "
          f"Depth 原生 shape = {views[0]['depth_native_shape']} "
          f"({'2x 超采样(opengl_gt), 已按 rigid_warp.py:78-80 resize' if views[0]['depth_native_shape'] != (views[0]['H'], views[0]['W']) else '与图像同分辨率(blender_gt)'})")
    print(f"[info] K(view0) =\n{views[0]['K']}")

    cfg = None
    if a.out_w and a.out_h:
        cfg = make_resize_cfg(views[0]["W"], views[0]["H"], a.out_w, a.out_h)
        print("[info] 尺寸对齐: %dx%d --crop--> %dx%d (off %d,%d) --scale %.6f--> %dx%d"
              % (views[0]["W"], views[0]["H"], cfg[0], cfg[1], cfg[2], cfg[3],
                 cfg[4], cfg[5], cfg[6]))
        for v in views:
            apply_resize(v, cfg, a.depth_resize)
        print(f"[info] 裁剪后 K(view0) =\n{views[0]['K']}")

    # ---- 外参 = inv(T) (A1/A3/B2) --------------------------------------
    Es = []
    for v in views:
        E = np.linalg.inv(v["T"])
        if a.negative_control == "transpose_R":
            E = E.copy(); E[:3, :3] = E[:3, :3].T        # 阴性对照
        elif a.negative_control == "flip_t":
            E = E.copy(); E[:3, 3] = -E[:3, 3]
        Es.append(E)
    if a.negative_control == "shuffle_depth":
        ds = [v["depth"] for v in views]
        for i, v in enumerate(views):
            v["depth"] = ds[(i + 1) % len(ds)]
    if a.negative_control != "none":
        print(f"[NEGATIVE CONTROL] 故意破坏: {a.negative_control}")

    # ---- 自证 ----------------------------------------------------------
    stats = {}
    if a.selfcheck:
        md, mz, mf = selfcheck(views, Es)
        stats["selfcheck_median_reproj_px"] = md
        stats["selfcheck_median_rel_depth_diff"] = mz
        stats["selfcheck_frac_geo_consistent"] = mf
        print(f"[SELFCHECK] 平面Z假设: 重投影中位残差 = {md:.4f} px | "
              f"相对深度差中位 = {mz:.6f} | 几何一致像素占比 = {mf:.4f}")
        md2, mz2, _ = selfcheck(views, Es, depth_as_ray=True)
        stats["selfcheck_ray_median_reproj_px"] = md2
        print(f"[SELFCHECK] 射线距离假设(对照): 重投影中位残差 = {md2:.4f} px | "
              f"相对深度差中位 = {mz2:.6f}")
        print(f"[SELFCHECK] 判定: 平面Z {'胜出 (与官方 reproject() 一致)' if md < md2 else '🔴 未胜出, 深度语义需重查'}")

    # ---- 逐帧深度范围 ---------------------------------------------------
    ranges = []
    for i, v in enumerate(views):
        r = depth_range(v["depth"], a.max_depth, a.relax_range)
        if r is None:
            print(f"[FATAL] view {i} 有效深度像素 < 100"); sys.exit(4)
        ranges.append(r)
    dmins = np.array([r[0] for r in ranges]); dmaxs = np.array([r[1] for r in ranges])
    covered = np.mean([ (valid_mask(v["depth"], a.max_depth) &
                         (v["depth"] >= r[0]) & (v["depth"] <= r[1])).mean()
                        for v, r in zip(views, ranges)])
    print(f"[info] depth_min: {dmins.min():.3f}~{dmins.max():.3f} m | "
          f"depth_max: {dmaxs.min():.3f}~{dmaxs.max():.3f} m | "
          f"落入 [min,max] 从而进 loss 的像素占比(均值) = {covered:.4f}")
    stats.update(depth_min_range=[float(dmins.min()), float(dmins.max())],
                 depth_max_range=[float(dmaxs.min()), float(dmaxs.max())],
                 loss_pixel_fraction=float(covered))

    # ---- 共视分数矩阵 ---------------------------------------------------
    n = len(views)
    score = np.zeros((n, n), dtype=np.float64)
    centers = [cam_center_from_E(E) for E in Es]
    for i in range(n):
        di = views[i]["depth"]; Ki = views[i]["K"]
        dmin_i, dmax_i = ranges[i]
        for j in range(n):
            if i == j:
                continue
            if a.score_rule == "infinigen_cov":
                score[i, j] = ig_covisibility(di, views[j]["depth"], Ki,
                                              views[j]["K"], views[i]["T"], views[j]["T"])
                continue
            mask, _, _ = check_geometric_consistency(
                di, Ki, Es[i], views[j]["depth"], views[j]["K"], Es[j], dmin_i, dmax_i)
            ys, xs = np.nonzero(mask)
            if len(xs) == 0:
                continue
            g = ((ys % a.score_grid) == 0) & ((xs % a.score_grid) == 0)
            xs, ys = xs[g], ys[g]
            if len(xs) == 0:
                continue
            zs = di[ys, xs]
            uv1 = np.stack([xs, ys, np.ones_like(xs)], axis=0).astype(np.float64)
            xyz_cam = np.linalg.inv(Ki) @ (uv1 * zs[None, :])
            pts_world = (views[i]["T"] @ np.vstack(
                [xyz_cam, np.ones((1, xyz_cam.shape[1]))]))[:3].T
            score[i, j] = calc_score_mvsnet(centers[i], centers[j], pts_world)
        print(f"  ref {i}/{n} 分数完成", flush=True)

    # colmap2mvsnet_np2.py:405-412
    num_view = min(a.num_view, n - 1)
    view_sel = []
    for i in range(n):
        order = np.argsort(score[i])[::-1]
        sel = [(int(k), score[i, k]) for k in order[:num_view]]
        if a.drop_zero_score:                 # DEV-9
            sel = [x for x in sel if x[1] > 0]
        view_sel.append(sel)
    nz = [sum(1 for _, s in sel if s > 0) for sel in view_sel]
    n_zero = sum(len(sel) - z for sel, z in zip(view_sel, nz))
    print(f"[info] num_view = min({a.num_view}, {n}-1) = {num_view}; "
          f"每 ref 非零分 src 数: min={min(nz)} median={int(np.median(nz))} max={max(nz)}")
    if n_zero:
        print(f"[warn] pair.txt 里共有 {n_zero} 条【分数=0】的 src (官方 np2:405-412 就是不过滤)。"
              f" blend.py 训练模式 random.sample 会把它们当正常 src 抽中 -> 无共视的监督对。"
              f" 要按 tartanground2mvsnet.py:433 的做法过滤请加 --drop_zero_score。")
    if min(len(s) for s in view_sel) < 7:
        print(f"[warn] 最少 src 数 = {min(len(s) for s in view_sel)} < 7 "
              f"=> blend.py:41-43 在 trainviews=8 下会丢掉这些 ref")
    stats.update(num_view=num_view, nonzero_src_min=int(min(nz)),
                 nonzero_src_median=int(np.median(nz)))

    if a.dry_run:
        print("[dry_run] 不落盘"); print(json.dumps(stats, indent=2)); return

    # ---- 落盘 -----------------------------------------------------------
    scan_dir = os.path.join(a.out, f"ig_{a.scan}")
    if os.path.exists(scan_dir) and not a.scan.startswith("neg"):
        print(f"[info] 覆盖已存在的 {scan_dir}")
    dI = os.path.join(scan_dir, "blended_images")
    dC = os.path.join(scan_dir, "cams")
    dD = os.path.join(scan_dir, "rendered_depth_maps")
    for p in (dI, dC, dD):
        os.makedirs(p, exist_ok=True)

    for i, v in enumerate(views):
        cv2.imwrite(os.path.join(dI, "%08d.jpg" % i), v["img"],
                    [cv2.IMWRITE_JPEG_QUALITY, JPEG_Q])
        save_pfm(os.path.join(dD, "%08d.pfm" % i), v["depth"].astype(np.float32))
        dmin, dmax = ranges[i]
        iv = (dmax - dmin) / max(DEPTH_NUM_FIELD - 1, 1)
        E, K = Es[i], v["K"]
        with open(os.path.join(dC, "%08d_cam.txt" % i), "w") as f:
            f.write("extrinsic\n")
            for r in range(4):
                f.write(" ".join("%.9f" % E[r, c] for c in range(4)) + " \n")
            f.write("\nintrinsic\n")
            for r in range(3):
                f.write(" ".join("%.9f" % K[r, c] for c in range(3)) + " \n")
            f.write("\n%.6f %.6f %d %.6f \n" % (dmin, iv, DEPTH_NUM_FIELD, dmax))

    # colmap2mvsnet_np2.py:442-449 (DEV-6: 分数格式)
    fmt = "%d %d " if a.score_rule == "mvsnet_count" else "%d %.6f "
    with open(os.path.join(dC, "pair.txt"), "w") as f:
        f.write("%d\n" % n)
        for i, sel in enumerate(view_sel):
            f.write("%d\n%d " % (i, len(sel)))
            for k, s in sel:
                f.write(fmt % (k, s))
            f.write("\n")

    meta = dict(scan=f"ig_{a.scan}", frames_root=os.path.abspath(a.frames),
                n_views=n, resolution=[views[0]["W"], views[0]["H"]],
                keys=[list(v["key"]) for v in views],
                K=[float(x) for x in views[0]["K"].ravel()],
                depth_native_shape=list(views[0]["depth_native_shape"]),
                score_rule=a.score_rule, depth_resize=a.depth_resize,
                relax_range=a.relax_range, negative_control=a.negative_control,
                crop_cfg=list(cfg) if cfg else None, **stats)
    with open(os.path.join(scan_dir, "conversion_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[done] 写出 {scan_dir} ({n} 视角)")
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
