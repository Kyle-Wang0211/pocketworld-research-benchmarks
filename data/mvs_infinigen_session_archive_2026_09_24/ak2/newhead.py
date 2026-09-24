import io, re
p = "arkit2blend_v2.py"
s = io.open(p, encoding="utf-8").read()
i = s.index('"""'); j = s.index('"""', i+3)
head = u'''"""ARKitScenes raw -> BlendedMVS 目录格式 (datasets/blend.py 原样能读) —— v2。

v1 = /root/arkit2blend.py (09-14)。v2 只补两个窟窿, 其余【逐字不动】:
  位姿写盘约定/内参容差/深度单位/关键帧规则/pair.txt/frame_range/write_pfm 全部沿用 v1,
  v1 的出处清单见 /root/arkit2blend.py 文件头, 此处不重复。

资产分档 (官方 raw/README.md 正文, 实测逐条核过):
  60 FPS  lowres_wide(256x192 RGB) / lowres_depth(256x192 Apple LiDAR) / confidence   [实测 58.82 Hz]
  10 FPS  wide(1920x1440 RGB) + highres_depth(1920x1440 FARO 激光投影)  —— 同一组时间戳, 互相同步
          官方原文: "filtered by high error between highres_depth and lowres_depth"
          ⇒ 这 10 FPS 不是简单抽帧, 是按 FARO 与 LiDAR 的误差筛过的子集
  30 FPS  vga_wide (640x480 RGB)                                                       [实测 30.30 Hz]
  位姿    lowres_wide.traj                                                             [实测 10.00 Hz]

=======================  v2 的两处改动 + 偏离清单  =======================

【改动 1】位姿配对: 5 ms 最近邻  ->  沿 traj 插值 (slerp + lerp)
  病灶(实测): traj 10.00 Hz 而 vga_wide 30.30 Hz。v1 用 tenFpsDataLoader.py:335 的
    |dt|<0.005 s 配对, /root/arkit_all.log 4866 个视频聚合: 11,917,129 帧里只有
    2,033,377 帧 (17.06%) 拿到位姿, 逐视频中位 17.10%; 另有 178 个视频因关键帧<12 整个被扔。
    highres_depth 那一组更惨: 2159 个视频 440,149 帧里只有 2.38% 能在 5 ms 内配上位姿。
  为什么官方没这个问题: 官方 tenFpsDataLoader 喂的是 lowres_* , 那条链的帧本来就取在
    traj 的同一时间网格上; 是我们换到 vga_wide / wide 才踩空。
  [偏离 D1] 官方 apple/ARKitScenes 仓 HEAD 474aaa8【没有】位姿插值实现 ——
    `grep -rn -iE "slerp|interp|lerp|quaternion" --include=*.py .` 的全部命中都是
    图像/特征图 resize (dataset.py:96 / image_utils.py:14 / msg.py:49 /
    MultiscaleConvDepthEncoder.py:65 / multi_scale_depth.py:52), 与位姿无关。
    => 无官方实现可抄。实现在 /root/ak_pose_interp.py: 旋转用 scipy
    spatial.transform.Slerp (与 tartanair_to_blend.py:25 已在用的同一个库), 平移用 np.interp。
  [偏离 D2] 在 camera->world 里插 (R_c2w 走 slerp, 相机中心 C 走 lerp), 不是对 traj 原始的
    t_w_to_p 线性插值 —— 相机中心才是物理上匀速的量。可证伪: space="w2c" 走另一条路。
  [偏离 D3] MAX_GAP=0.20 s (=2 倍标称周期) 守卫 + 禁止外推。无官方出处。
    17 个视频实测 traj 间隔 p99=0.09996 s / max=0.117 s / >0.2 s 的洞 0 个
    ⇒ 正常视频上这条闸不拒绝任何帧, 只在 ARKit 跟丢的视频上兜底。
  自证 A (留出法, /root/ak_pose_interp_check.py, 17 个视频):
    把 10 Hz traj 抽稀到 0.2 s, 在【被丢掉的中点】插值与真值比 —— 四条腿:
      interp(c2w) 正解        中位 2.75 mm / 0.450 deg
      interp(w2c) 阴性对照 A  中位 4.12 mm             (在错的空间里插, 更差 ✓)
      nearest     阴性对照 B  中位 27.30 mm / 2.962 deg (不插值取最近, 差 10 倍 ✓)
      const       阴性对照 C  中位 1400-3000 mm        (无信息下界 ✓)
    误差 ~ gap^1.49 ⇒ 真实工况 (0.1 s 洞) 中位 ≈ 1 mm【推断, 无真值可留出】。
  自证 B (真实工况, /root/ak_v2_probe.py --what pose, 41048190, 时间密度对齐):
      A 精确帧 + traj 原值   跨视中位|dz| 0.0032 m   (v1 唯一收的那 16.74%)
      B 插值帧 + slerp/lerp  跨视中位|dz| 0.0046 m   (v1 全扔的那 83.26%) <- 与 A 同档 ✓
      C 插值帧 + 最近邻位姿   跨视中位|dz| 0.0083 m                       <- 必须更差 ✓
      D 插值帧 + 位姿写反     跨视中位|dz| 0.0791 m                       <- 必须爆掉 ✓

【改动 2】深度真值: 手机 LiDAR 上采样  ->  FARO 激光扫描仪原生 1920x1440 降采样
  病灶(实测): v1 用 lowres_depth (256x192), INTER_NEAREST 拉到 768x576 ⇒ 3x3 块内全是复制品。
    实测 768x576 上 "2x2 邻块非常数" 比例只有 0.487 (x3 复制的理论上限 0.556),
    blend.py 的 stage3(384x288) -> stage4(768x576) 新增深度值 = 0 个。
  v2 在有 highres 的视频上【整组换掉】: RGB=wide, K=wide_intrinsics, 深度=highres_depth,
    位姿=traj 插值。输出分辨率仍是 768x576 (训练分辨率不动)。
    换后 2x2 非常数 0.995; 退化对照 (把 FARO 也压成 256x192 再拉回) 掉到 0.552 ⇒ 尺子会报警 ✓
    stage3->stage4 新增深度值 19,263 个 (v1 是 0)。
  为什么不是 "RGB 继续用 vga_wide, 只换深度" (实测否决):
    41048190 实测 787 个 highres 时间戳与 7557 个 vga_wide 时间戳【零重合】,
    最近的 vga 帧 |dt| 中位 16.0 ms / max 17.0 ms, <5 ms 的 0 个 ⇒ RGB 与深度会错开一帧。
    而 wide 与 highres_depth 同时间戳。且 wide.zip 1.49 GB < vga_wide.zip 2.79 GB, 更省。
    顺带修掉 v1 的一个隐藏窟窿: 640x480 -> 768x576 是【放大】1.2 倍 (INTER_AREA 在放大时
    不做任何平均); v2 是 1920x1440 -> 768x576 的真降采样。
  [偏离 D4] `wide` / `wide_intrinsics` 不在 download_data.py:13-15 的 choices 里 (官方 CLI
    取不到), 但官方 raw/README.md 正文把它们列为 raw 的正式资产, 且同一个 URL 前缀
    {ARkitscense_url}/raw/{split}/{video_id}/wide.zip 实测 HTTP 200。下载走 /root/ak2_fetch.sh,
    URL 拼法逐字照 download_data.py:7,176,193-200。
  [偏离 D5] 深度降采样用【带有效掩码归一化的 INTER_AREA】:
        num = resize(d*m, AREA); den = resize(m, AREA); out = num/den (den>0), 否则 0
    官方对深度一律 INTER_NEAREST (dataset.py:96; DUSt3R preprocess 同)。这里偏离是用户拍板:
    2.5 倍降采样下 NEAREST 会扔掉 84% 的激光样本。掩码归一化是为了不让 0 参与平均把深度拉向 0
    (官方 valid_depth_mask.py 也认定 highres_depth != 0 为有效)。
    副作用实测: area 与 nearest 差 >5% 的像素只占 0.07% ⇒ 跨深度断崖的"飞点"可忽略。
    `--depth_resize nearest` 可切回官方口径做单变量对照。
  [偏离 D6] highres_depth 有洞 (FARO 投影盲区), v1 的 lowres_depth 是 100% 有效。
    洞在 blend.py:135-139 的 mask 里被 `depth >= depth_min` 排除 (depth_min 来自 frame_range
    的 p1, 只统计 d>0) ⇒ 结构上安全。实测 5 个视频: 原生有效率 0.929-0.945,
    768x576 上 0.934-0.955; 过 blend.py 后 stage4 mask 有效比例 中位 0.9335 (p10 0.780),
    对照 LiDAR 臂 0.9805 ⇒ 监督像素净损失约 4.7 个百分点。
  K 的端到端自证 (41048190, 787 帧): wide_intrinsics / vga_wide_intrinsics =
    cx 2.999997 (p1 2.999908 / p99 3.000076), cy 3.000000, fx/fy 中位 3.000000
    (p1 2.987 / p99 3.014, 这个散布全部来自两路内参流相差 16 ms 的对焦漂移, 因为 cx/cy 不漂)。
    ⇒ x3 成立; 但 v2 并不依赖它 —— 直接用官方 wide_intrinsics。
    光度自证 (/root/ak_photo_probe.py, 基线对齐): 正解 3.54 / RGB 换邻帧 7.31 / 位姿写反 15.25
    ⇒ wide <-> highres_depth <-> wide_intrinsics <-> 插值位姿 这条链配对正确 ✓

  代价 (如实): highres 那一组是"按 FARO/LiDAR 误差筛过"的稀疏子集, 2159 个视频实测
    只有 440,149 帧 (中位 149 帧/视频), 关键帧 223,950, 是 v1 在同一批视频上的 0.655 倍
    (逐视频中位 0.625)。换 FARO 真值要付 ~35% 的关键帧。
  没做到的 (如实): 我【没能】用一个会报警的判据证明 FARO 比 LiDAR 在【米制精度】上更准 ——
    光度重投影在 0.3 m 基线下对 "深度整体 x1.02" 只给出 +4.8%, 而 FARO vs LiDAR 只差 0.9%
    (噪声内)。能证明的是【分辨率/细节】那一层 (见上) 以及两者同框 (中位差 13.6 mm)。
    "FARO 是真值" 这一条是官方措辞 (upsampling README: "the ground-truth depth image
    projected from the mesh generated by Faro's laser scanners"), 不是我测出来的。

  没有 highres 的视频 (4869-2172=2697 个) 走 --depth lowres, 即 v1 的资产组合
  (vga_wide + lowres_depth) + 改动 1 的插值, 深度那一层维持 v1 原状。
"""'''
io.open(p, "w", encoding="utf-8").write(head + s[j+3:])
print("header rewritten, %d bytes" % len(head + s[j+3:]))
