# -*- coding: utf-8 -*-
"""TG 转换器加 --pair_rule dvmvs: 长轨迹(关键帧 1,490 帧)下 colmap2mvsnet 角度分数要对每对做稠密重投影 O(n^2) 张图, 不可行;
改用 deep-video-mvs 罚分 (pose_distance/calculate_penalty 逐字在 tartanair_to_blend.py), 权重 1/(1+penalty)
与 tartanair_to_blend.write_pairs 同式, 第 4 步按分数降序取 num_src => 与 TartanAir 完全同一选源规则 (同一出处)。"""
p = "/root/tartanground2mvsnet.py"
s = open(p).read()
pairs = [
 ('    ap.add_argument("--num_src", type=int, default=10, help="pair.txt 每个 ref 保留的 src 数")\n',
  '    ap.add_argument("--num_src", type=int, default=10, help="pair.txt 每个 ref 保留的 src 数 (colmap2mvsnet sorted_score[:10])")\n'
  '    ap.add_argument("--pair_rule", choices=["score", "dvmvs"], default="score",\n'
  '                    help="score = colmap2mvsnet 角度分数(需稠密重投影, 长轨迹不可行); "\n'
  '                         "dvmvs = deep-video-mvs 罚分 1/(1+penalty), 与 tartanair_to_blend.write_pairs 同式, 只用位姿")\n'),
 ('    rng = np.random.default_rng(0)\n    score = np.zeros((n, n), dtype=np.float64)\n    for i in range(n):\n        depth_i = depths[i]\n',
  '    rng = np.random.default_rng(0)\n    score = np.zeros((n, n), dtype=np.float64)\n'
  '    if args.pair_rule == "dvmvs":\n'
  '        # deep-video-mvs keyframe_buffer.py get_best_measurement_frames 的罚分; 权重 1/(1+penalty) = tartanair_to_blend.write_pairs 同式\n'
  '        sys.path.insert(0, "/root/ta2")\n'
  '        from tartanair_to_blend import pose_distance, calculate_penalty\n'
  '        c2w = [np.linalg.inv(E) for E in Es]\n'
  '        for i in range(n):\n'
  '            for j in range(n):\n'
  '                if i != j:\n'
  '                    _, R_m, t_m = pose_distance(c2w[i], c2w[j])\n'
  '                    score[i, j] = 1.0 / (1.0 + calculate_penalty(t_m, R_m))\n'
  '        print("[info] pair_rule=dvmvs: score=1/(1+penalty), %d x %d" % (n, n))\n'
  '    for i in (range(n) if args.pair_rule != "dvmvs" else []):\n        depth_i = depths[i]\n'),
]
for old, new in pairs:
    assert s.count(old) == 1, (s.count(old), old[:60])
    s = s.replace(old, new)
open(p, "w").write(s)
print("TG pair_rule patch ok")
