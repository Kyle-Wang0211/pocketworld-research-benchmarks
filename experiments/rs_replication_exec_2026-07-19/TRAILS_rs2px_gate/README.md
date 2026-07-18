# E2-B:RS 默认 2.0px 重投影裁剪套用到 cap50 —— "RS 为什么没拖尾"头号假说检验

日期 2026-07-18(exec 批次名沿用 2026-07-19)。研究产物,不改生产;无 git 操作(编排者统一提交)。
RS 键值:`Max feature reprojection error = 2.0 px`(VERIFIED,官方键值表)vs 我们生产 4px(BA 后 filter)/ 10px(live create)。RS mobile 内部实现 = UNRESOLVED 红线,本实验只检验"2.0px 门"这一个可证变量。

## 裁决(headline)

**假说大部分被否证:2.0px 重投影门不是 RS 零拖尾的主机制,且绝不是免费刀。**

1. **选择性弱(~1.7–2×,不是手术刀)**:在 rebuilt@4px 基线(90,755 点)上,2.0px 杀 18,760 点(20.7%);
   拖尾签名点(SIG_ISO 孤立点)杀灭率 30.5%、hull 外 >1m 远拖尾区杀灭率 37–42%,
   但密集真面核心(DENSE)误杀率 17.5%——红点在 diff 渲染里遍布墙面/地板,不集中在拖尾热区。
2. **远拖尾杀不干净**:hull 外 >1m 点 1,604 → 962(2.0px),仍 ~2× 生产云水平(489)。
3. **真正的拖尾杀手另有其人(最有价值的意外发现)**:纯 reproj 门族(无三角角度/floater 门)的 4px 重建云
   有 1,604 个远拖尾点,而生产云(带 tri-angle 2°/floater 门)只有 489 —— **角度/track 拓扑类门的拖尾压制
   力 ~3.3×,远强于把 reproj 门从 4 收到 2**。RS 的零拖尾更可能来自其未公开的组合闸(红线,不可声称)。
4. **质量无损硬门:2.0px 不过**。地板正确覆盖 2,111 → 1,813 格(−14.1%),违反质量北极星;
   地板厚度仅 0.0465 → 0.0429 m(−7.8%),厚度收益配不上覆盖损失。3px 档:覆盖 −3.6%、厚度 −4.4%,同样非免费。
5. **误杀重灾区=长 track**:per-obs 残差随 track 长度增长(2-view 中位 0.81px;10+ 观测 track 中位 2.86px、p90 10.3px)
   —— 收紧 obs 门首先撕咬的是多视角强约束点的观测,与"弱纹理墙点 reproj 偏大"记忆一致。

操作点曲线见 `operating_curve.png`:任何 <4px 的档位,拖尾杀灭率与真点误杀率近似同步上升,无甜点。

## 方法(v2,track 空间;v1 被否证已归档)

- **v1 否证**:以生产 PLY 点位反找 6px 内最近 verified keypoint 当观测 → 4px 控制组本应 ~0 实裁 17.4%,
  且"残差"直方图 ∝ r(均匀随机关联特征)→ 方法学作废,归档在 `_v1_deprecated_pointanchor/WHY_DEPRECATED.md`。
- **v2**:union-find 重建 track(738 对 two_view_geometries,252,014 inlier 边 → 96,595 条 ≥2 帧 track)
  → 精化生产位姿 + 冻结 K 多视 DLT → **每观测**重投影残差 → RS 语义:obs>gate 删观测,幸存 obs 从头重三角化并
  迭代至收敛(≤5 轮),点存活须 ≥2 观测/≥2 帧(RC tie point 定义)。扫 1.5/2.0/2.5/3.0/3.5/4.0px。
- **同 gauge**:全程生产精化位姿坐标系直出,禁 Sim3、零对齐(S1 probe_gauge 已证 PLY 系==meta 系)。
- **真彩**:认证配方(幸存 track 观测 → 3840×2160 全分辨率 bilinear → 均值 → round);24 帧照片缺失导致
  ~5.4k 点走生产云 NN≤5cm 回退补色(`color_fallback.json`,已在 PLY comment 声明),~100–160 点无 NN 保持灰色。
- **拖尾签名(自算简版,E2-A 并行未交付,落地后须对账)**:SIG_ISO = d10>3×中位(61.8mm)孤立点 8,370;
  DENSE = d10<中位(20.6mm)密集核 45,377;相机 XZ 凸包外距离分带(墙体在 0–1m 带,>1m = 真拖尾区)。

## 验证与诚实边界

- **控制组自检过**:4.0px 档对基线杀 0(定义一致性);rebuilt@4px vs 生产云 NN p50=14.8mm,与已知 ~1cm
  沿射线散射一致(重建 track ≠ 生产逐字节 track 身份,声明为近似)。
- **0.56px 复现失败(部分)**:全体 per-obs 残差中位 1.363px,非先前口径的 0.56px;分解表明 2-view track
  中位 0.807px,多视长 track 拉高中位 —— 先前 0.56px 大概率是 2-view/逐对三角化口径(`aux_checks.json`)。
- 本实验基线是 rebuilt@4px(唯一变量=门值,控制变量纪律),生产云只作 context,不能拿生产云直接当控制组。
- RS 语义近似:一趟 obs-cull + 重三角化迭代;RS 真实内部(BA 交替、mobile 档差异)UNRESOLVED,不声称逐字节。
- 墙钟为 host python 代理(全程 14.1s),非设备数;Mac 内存 vm_stat 自检通过(free ≥ 0.3GB 全程无压力)。

## 产物清单(SHA 见 SHA256SUMS.txt)

- `rs2px_cap50.ply`(71,995)/ `mid3px_cap50.ply`(85,083)/ `ours4px_cap50.ply`(90,755)—— 三档候选,同 gauge 真彩
- `diff_killedby2px_cap50.ply` —— 灰=4px 基线幸存,红=被 2.0px 杀
- `compare_truecolor_top.png` / `compare_truecolor_elev.png` —— 生产 vs 4px vs 2px 三联并排
- `diff_killedby2px.png` —— 红点空间分布(俯视+立面,蓝线=相机 hull)
- `operating_curve.png` —— 拖尾杀灭率 vs 真点误杀率 vs 覆盖损失操作点曲线
- `stats_v2.json` / `aux_checks.json` / `color_fallback.json` —— 全量数字
- `rs_gate_sweep_v2.py` / `aux_checks.py` / `finalize_renders.py` —— 可复跑脚本(python3.11)

## 网页肉眼并排(用户批准用)

```bash
cd /Users/kaidongwang/.config/superpowers/worktrees/pocketworld_research_benchmarks/pocketworld-repro-contract-20260714
python3.11 -m http.server 8123
# 我们4px vs RS2px:
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=TRAILS_rs2px_gate/ours4px_cap50.ply&right=TRAILS_rs2px_gate/rs2px_cap50.ply"
# 生产云 vs RS2px:
open "http://localhost:8123/experiments/rs_replication_exec_2026-07-19/compare_any.html?left=../../data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_sparse.ply&right=TRAILS_rs2px_gate/rs2px_cap50.ply"
```

## 对下游的建议(留编排者/用户裁决)

- 2.0px 直接照抄 = 否决候选(覆盖 −14.1% 违反无损硬门);
- 拖尾歼灭的杠杆应指向 **角度/出生拓扑类门**(与 stage-1"产跨边+定出生"、E2-A 拖尾集、mirror-cull 方向合流),
  而非全局收紧 reproj;若要 reproj 层面动作,只该考虑**分区/分签名**的门(如仅对 hull 外/孤立签名点收紧),须另立实验。
