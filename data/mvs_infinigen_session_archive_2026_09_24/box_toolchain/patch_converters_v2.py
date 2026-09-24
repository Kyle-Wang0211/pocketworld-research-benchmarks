# -*- coding: utf-8 -*-
"""给 TartanAir / TartanGround 转换器打"有出处"补丁 (精确字符串替换, 找不到就报错):
  ① 取帧: stride/max_frames -> deep-video-mvs 关键帧规则 (keyframe_buffer.py try_new_keyframe:
         与上一关键帧 pose_distance >= keyframe_pose_distance; config.py test_keyframe_pose_distance=0.1)
  ② min_frames -> 8 (= blend.py:41 nviews-1=7 个源视图 + 1 个 ref 的最低要求)
  ③ TG 共视分数采样: 随机 4000 像素 -> 步长 8 的规则网格 (CasDiffMVS stage1 = 1/8 分辨率, blend.py:127)
  JPEG 95 = OpenCV grfmt_jpeg.cpp `int quality = 95;` 默认, 不改。"""
import sys

def patch(path, pairs):
    s = open(path).read()
    for old, new in pairs:
        if s.count(old) != 1:
            sys.exit("PATCH FAIL %s: %d matches for %r" % (path, s.count(old), old[:70]))
        s = s.replace(old, new)
    open(path, "w").write(s)
    print("patched", path)

# ---------------- TartanAir ----------------
TA = "/root/ta2/tartanair_to_blend.py"
patch(TA, [
    ('    ap.add_argument("--stride", type=int, default=1, help="帧抽样步长, 控制总组数")\n'
     '    ap.add_argument("--min_frames", type=int, default=12)\n',
     '    ap.add_argument("--stride", type=int, default=1, help="帧抽样步长 (无出处, v2 不用; keyframe_dist>0 时忽略)")\n'
     '    ap.add_argument("--keyframe_dist", type=float, default=0.0,\n'
     '                    help=">0: deep-video-mvs 关键帧规则, 与上一关键帧 pose_distance>=该值才收 (config.py test_keyframe_pose_distance=0.1)")\n'
     '    ap.add_argument("--min_frames", type=int, default=8, help="= blend.py:41 nviews 8 的最低帧数")\n'),
    ('                keep, poses, depths, colors, bad = [], [], [], [], 0\n'
     '                for i in range(0, len(imgs), a.stride):\n'
     '                    T = world_T_cam(rows[i])\n'
     '                    ok, why = rotation_is_valid(T[:3, :3])\n'
     '                    if not ok: bad += 1; continue\n',
     '                keep, poses, depths, colors, bad = [], [], [], [], 0\n'
     '                if a.keyframe_dist > 0:      # deep-video-mvs keyframe_buffer.py try_new_keyframe\n'
     '                    sel, last = [], None\n'
     '                    for i in range(len(imgs)):\n'
     '                        T = world_T_cam(rows[i])\n'
     '                        if not rotation_is_valid(T[:3, :3])[0]: continue\n'
     '                        if last is None or pose_distance(last, T)[0] >= a.keyframe_dist:\n'
     '                            sel.append(i); last = T\n'
     '                else:\n'
     '                    sel = list(range(0, len(imgs), a.stride))\n'
     '                for i in sel:\n'
     '                    T = world_T_cam(rows[i])\n'
     '                    ok, why = rotation_is_valid(T[:3, :3])\n'
     '                    if not ok: bad += 1; continue\n'),
])

# ---------------- TartanGround ----------------
TG = "/root/tartanground2mvsnet.py"
patch(TG, [
    ('    ap.add_argument("--stride", type=int, default=5, help="按此步长从轨迹中抽帧")\n'
     '    ap.add_argument("--max_frames", type=int, default=150)\n',
     '    ap.add_argument("--stride", type=int, default=5, help="按此步长从轨迹中抽帧 (无出处, v2 不用; keyframe_dist>0 时忽略)")\n'
     '    ap.add_argument("--max_frames", type=int, default=0, help="0 = 不截断 (v2); 旧值 150 无出处")\n'
     '    ap.add_argument("--keyframe_dist", type=float, default=0.0,\n'
     '                    help=">0: deep-video-mvs 关键帧规则 (config.py test_keyframe_pose_distance=0.1)")\n'
     '    ap.add_argument("--min_frames", type=int, default=8, help="= blend.py:41 nviews 8 的最低帧数")\n'
     '    ap.add_argument("--score_grid", type=int, default=0,\n'
     '                    help=">0: 共视分数用步长 score_grid 的规则网格像素 (8 = CasDiffMVS stage1 1/8 分辨率, blend.py:127); 0 = 旧的随机 score_sample_pixels")\n'),
    ('    else:\n'
     '        frame_ids = list(range(0, n_total, args.stride))[:args.max_frames]\n'
     '        print(f"[info] 抽帧 stride={args.stride} -> 选中 {len(frame_ids)} 帧: "\n'
     '              f"{frame_ids[0]}..{frame_ids[-1]}")\n',
     '    elif args.keyframe_dist > 0:\n'
     '        # deep-video-mvs keyframe_buffer.py try_new_keyframe: 与上一关键帧 combined pose_distance >= 阈值才收\n'
     '        sys.path.insert(0, "/root/ta2")\n'
     '        from tartanair_to_blend import pose_distance\n'
     '        frame_ids, last = [], None\n'
     '        for i in range(n_total):\n'
     '            T = ned_pose_to_cv_cam2world(poses[i])   # 与逐帧写 cam.txt 同一函数 (c2w, CV 相机系)\n'
     '            if last is None or pose_distance(last, T)[0] >= args.keyframe_dist:\n'
     '                frame_ids.append(i); last = T\n'
     '        print(f"[info] dvmvs 关键帧 (>= {args.keyframe_dist}) -> {len(frame_ids)}/{n_total} 帧")\n'
     '    else:\n'
     '        frame_ids = list(range(0, n_total, args.stride))\n'
     '        if args.max_frames > 0: frame_ids = frame_ids[:args.max_frames]\n'
     '        print(f"[info] 抽帧 stride={args.stride} -> 选中 {len(frame_ids)} 帧: "\n'
     '              f"{frame_ids[0]}..{frame_ids[-1]}")\n'
     '    if len(frame_ids) < args.min_frames:\n'
     '        print(f"[SKIP] 帧数 {len(frame_ids)} < min_frames {args.min_frames}"); sys.exit(3)\n'),
    ('            if len(xs) > args.score_sample_pixels:\n'
     '                sel = rng.choice(len(xs), size=args.score_sample_pixels, replace=False)\n',
     '            if args.score_grid > 0:\n'
     '                g = ((ys % args.score_grid) == 0) & ((xs % args.score_grid) == 0)\n'
     '                xs, ys = xs[g], ys[g]\n'
     '            if args.score_grid <= 0 and len(xs) > args.score_sample_pixels:\n'
     '                sel = rng.choice(len(xs), size=args.score_sample_pixels, replace=False)\n'),
])
