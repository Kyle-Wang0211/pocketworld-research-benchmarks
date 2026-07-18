# E16 终审判决书 — M2 低视差出生禁令(ORB-SLAM2 baseline/medianSceneDepth 出生闸)

日期 2026-07-18(exec 目录沿用 07-19 批次)。单线完成实现+编译+smoke+矩阵+法医。
铁律执行:**A worktree tracked 脏集零改动**(结束态 `git diff --stat` = 13 files +3603/−1411 逐字同,
`bench/aether_sfm_c.cc` SHA 仍 `ad478da3…ca23`);全部改动只在 E12 已建 untracked 副本
`build-host-e12-stage2/aether_sfm_c_e12.cc` 上;零 commit;编译 -j2 配方(单 TU 逐字 flags);
运行前 vm_stat 门 5.0-6.1 GB > 3 GB 全程满足;off×3 基线复用 E9 在库 runs(未重跑)。

## 总判决(先说结论)

⚪ **签决阈值下 M2 是构造性无操作(no-op)——不是"效果小",是一对都禁不到**:两 cap 全部时间对的
baseline/medianSceneDepth 最小值 = **0.0202(cap51)/ 0.0283(cap50)**,ORB-SLAM 默认阈值 0.01 与
2× 加严 0.02 都够不着任何一对(0.01 臂遥测 banned=0/0;云与 OFF 逐点一致,diff 红点 = 0)。
**鬼带压缩 0,墙覆盖代价 0,交换比 0/0——没有取舍可签。**

🔴 **强行加压到能咬合的阈值后,机制轴向错配暴露:M2 先杀墙、最后才碰鬼**。
ratio=0.05(禁 1% 对)在 OFF 固定框架下的原位丢失归因:**墙 65.3% / 物体 44.6% / 真地板 25.2% /
鬼带仅 0.98%**——记忆锚"~80% 低视差 2-view = 故意保留的弱纹理墙覆盖"被定量坐实,且鬼带恰恰
不是这些对生的。ratio=0.15(禁 12% 对)才压到鬼带(原位丢失 80.8%),但真地板 41.2%、墙 78.0%
陪葬 + 位姿 gauge 破碎(warp 中位 21.1mm / p90 111mm),E12 stage2 同族的结构摧毁,不是清创。

**物理定数**:σ_depth 鬼壳的"低视差"是**点级三角化角**病理(双墙判决书:5.2° 厚 vs 11.4° 薄),
而 M2 量的是**对级 baseline/中位深度**——同一个词,不同的轴。步行 dome 采集里对级 ratio 天然
健康(p50 0.47/0.57,最小 0.02),鬼点生于 ratio 健康、点级视差角却低的几何(掠射地板)。
点级的等价旋钮就是已认证的 tri-angle 2.0° 门(T15/T20 扫过并定价)。**对级出生禁令救不了点级病。**

---

## 1. 实现与红线(全绿)

- **机制(自实现,ORB-SLAM2 `LocalMapping::CreateNewMapPoints` 判据)**:2-view 出生前,对
  (pair) 级算 `baseline/medianSceneDepth`,< 阈值(env `AETHER_M2_LOWPARALLAX_MIN_RATIO`,默认
  0.01)**拒绝出生**;中位深度 = ORB-SLAM `ComputeSceneMedianDepth(q=2)` 语义(该帧观测到的
  当前重建点在其相机系的中位 z,`(N-1)/2` 位序),live 侧用 established 邻帧(prev)+ FrameRecord
  位姿(与该口出生门同 gauge),temporal_detail 侧用 pair 晚帧(frame2)+ recon 位姿(同上)。
  无可算深度(bootstrap)= 放行(ORB-SLAM 同语义:初始化后才有此门)。
- **两个出生口都挂了**:live 2-view create(`aether_sfm_c_e12.cc` 普通 create 链前)+
  finalize temporal_detail create(`RestoreTemporalDetail` create 链前);**grow/merge/其他臂
  文本零改动**;env 不设 = 臂完全休眠(默认 OFF 纪律)。
- env 臂:`AETHER_M2_LOWPARALLAX_BAN=1`(+ `AETHER_M2_LOWPARALLAX_MIN_RATIO`);
  遥测:live 20 帧节律 `m2-lowparallax` 行 + finalize `m2-lowparallax-td` 行(7 个计数器)。
- 产物 SHA(`SHA256_BINARIES.txt`):源副本(改后)`d79dc3cf…994c`;改前副本经
  E12 diff 重建对账 = `97846ba1…a515` **逐字命中 E12 BUILD.md 记录**;E16 exe
  `sfm_replay_bench_e16_exe` = `91e400dd…af37`;E12 exe / 基线 exe 未动(SHA 逐字同 E12 记录)。
  swap 有效性:E16 exe 含 M2 env 串 ×2,基线/E12 exe 均 0。diff = `e16_vs_e12_copy.diff`(198 行)。
- 编译/链接零警告零错误(`build-host-e12-stage2/e16_compile.log`、`e16_link.log` 皆空)。

| 跑(runs/) | rc | n_reg | n_points | reproj | 断言红线¹ | M2 遥测(live banned / td banned) |
|---|---|---|---|---|---|---|
| cap51_m2(0.01) | 0 | **105 不掉** | 65,928 | 0.8623 | 0 | **0**/842 对,**0** 出生禁;td **0**/570 |
| cap50_m2(0.01) | 0 | **139 不掉** | 93,274 | 0.9623 | 0 | **0**/997 对;td **0**/738 |
| cap51_e16exe_envoff | 0 | 105 | 65,927 | 0.8626 | 0 | 遥测串 0 出现 = env 不开完全休眠 |
| cap51_m2_r002(0.02) | 0 | 105 | 65,929 | 0.8624 | 0 | live 0;td **1 对 / 1,138 出生禁** → 净 ±1 点(冗余补偿²) |
| cap51_m2_r005(0.05) | 0 | 105 | 65,482 | 0.8663 | 0 | live 9 对/5,858;td 7 对/4,671 |
| cap51_m2_r015(0.15) | 0 | 105 | 46,944 | 0.8836 | 0 | live 99 对/54,050;td 91 对/31,960 |

¹ `must not contain duplicate matches` / `THROW_CHECK_LE` 两式 grep 全 0。
² 0.02 恰好压住全库最低 ratio 对(0.0202,recon gauge 咬到、live ARKit gauge 没咬到):该对的
1,138 次 create 被拒后,同 site 点从其他对照常出生 —— **对级禁令有强冗余补偿,单对禁令≈无损也≈无效**。
smoke(cap51,`smoke/cap51_m2_smoke/`)同全绿:rc=0 / n_reg=105 / 断言 0 / banned=0。

## 2. 为什么签决阈值构造性零咬合(ratio 分布,一手实测)

对 E9 在库 off bin 模型逐对复算(`ratio_diag.py` → `analysis/ratio_distribution.txt`,
temporal 窗 gap≤12 全对集):

| | n_pairs | min | p1 | p5 | p50 | banned@0.005 | @0.01 | @0.02 | @0.05 | @0.15 |
|---|---|---|---|---|---|---|---|---|---|---|
| cap51 | 1,182 | **0.0202** | 0.053 | 0.108 | 0.472 | 0 | **0** | 0 | 11(0.9%) | 109(9.2%) |
| cap50 | 1,590 | **0.0283** | 0.068 | 0.131 | 0.565 | 0 | **0** | 0 | 7(0.4%) | 110(6.9%) |

ORB-SLAM 0.01 门针对的是**近静止关键帧对**(三脚架/纯旋转);本采集是步行 dome:任意时间对
最小基线 3.1cm、中位深度 1.1-1.5m → 最小 ratio ≈ 0.02-0.03,**协议本身就不产 M2 要禁的对**。
换算:ratio 0.01 ≈ 中位深度处 0.57° 视差角,**远弱于生产点级 tri-angle 2.0° 门**(≈ratio 0.035)——
在 0.035 以下 M2 全被现有门支配,以上则开始比现有门更钝(整对连坐 vs 逐点裁决)。
**矩阵适配(如实申报)**:签决扫描档 0.005/0.01/0.02 中,0.005 被 0.01 的 banned=0 严格支配
(子集论证)故不烧跑;0.02 是边界(实跑,咬 1 对);为让交换比可定价,增补 0.05/0.15 两档
(最小能咬合的阈值),理由与数据全录 `run_e16.sh` 注释。

## 3. 固定框架量(E12 主尺 = 生产原框;E8 常量;off×3 中位基线)

**cap51(主测床;回放近确定性:off×3 floor_peak 互差 ±1 点,m2 与 off 逐点一致)**

| 指标 | off×3 中位 | m2(0.01) | r002 | r005 | r015 |
|---|---|---|---|---|---|
| 真地板峰 [−7.5,+12.5)mm | 11,499 | 11,497(−0.02%) | 11,499(±0) | 5,039(−56%)³ | **633(−94.5%)**🔴 |
| 鬼带 [−45,−20)mm | 7,034 | 7,032(−0.03%) | 7,026(−0.1%) | 8,484(+21%)³ | 3,485(−50.5%) |
| 双峰对比度(鬼峰/地板峰,5mm bin) | 0.345 | 0.343 | 0.344 | 1.92³ | 3.00🔴 |
| 覆盖 2cm 格(重锚帧) | 3,647 | +0.2% | +0.3% | +50.1%³伪影 | −14.2% |
| below-floor(<−100mm) | 120 | 120 | 119 | 110 | 95 |
| 位姿翘曲 vs off_r2(中位/p90 mm) | — | 0.1/0.1 | 0.1/0.3 | 0.1/**282**🔴 | 21.1/**111**🔴 |
| 分面:地板 slab n | 21,796 | −0.0% | −0.0% | −0.6% | −40.9% |
| 分面:主墙 slab n(固定墙框) | 8,108 | −0.1% | −0.0% | **−67.9%**🔴 | −62.9%🔴 |
| 分面:墙覆盖 2cm 格 | 1,615 | −0.1% | +0.0% | **−59.6%**🔴 | −49.9%🔴 |
| 分面:物体(其余) | 36,022 | +0.0% | +0.0% | +14.4%³ | −13.8% |

³ **r005 框架法医(E12 教训重演,标注防误引)**:9+7 对被禁后 BA 走到另一收敛枝——位姿中位没漂
(0.1mm)但 p90 残差 282mm(部分相机移位数十 cm),锚移 −15.1mm;raw 尺的地板峰−56%/鬼带+21%
与重锚尺的 truefloor+11%/cover+50% **互相矛盾,皆不可引用**;可信的是 warp-免疫归因(§4)与肉眼
(§6:横截面出现斜向红标糊带 = gauge 碎裂特征)。r015 的 raw 读数方向可信(锚移 −16.7mm 但形态
上双层俱毁),精确幅度同样受 21mm 中位翘曲污染。

**cap50(泛化;banned=0 → m2 = off 的又一采样)**:m2 云对 off_r2 **absent=0 / new=0**(2cm),
机制账本 banned=0 ⇒ 一切 raw 带差异都是噪声的实测:鬼带 579 vs off×3 646-648(−10.7%)、
below-floor 435 vs 441 —— **cap50 host 鬼指标单跑噪声 ≥±10% 再证**(47 号抽签纪律),
不得引为效果。off×3 自身 floor_peak 3,669-3,793(±1.7%)同示噪声带。

## 4. 被禁出生的点在哪(warp-免疫归因:OFF 固定框架下"原位丢失"分面账,cap51)

红点 = off_r2 云中在该臂云 2cm 内无对应的点(= 被禁出生 + 解重排;运行噪声地板:off_r1 vs off_r2
同尺 = **0.002%**,故 m2/r002 的 0 与 1 点即字面零):

| 臂 | 原位丢失总量 | 地板 slab | 真地板带 | **鬼带** | **主墙 slab** | 物体 |
|---|---|---|---|---|---|---|
| m2(0.01) | **0(0.00%)** | 0% | 0% | 0% | 0% | 0% |
| r002 | 1 点(0.00%) | 0% | 0% | 0% | 0% | 0% |
| r005 | 24,755(37.5%)⁴ | 15.6% | 25.2% | **0.98%** | **65.3%**🔴 | 44.6% |
| r015 | 44,349(67.3%)⁴ | 52.4% | 41.2% | **80.8%** | **78.0%**🔴 | 73.8% |

⁴ r005 同时 new=25,966(净点数只 −0.7%)——大头是**整体重排**而非删除;但"什么面丢了原位几何"
的排序不受此混淆:**墙第一个死,鬼带最后一个死**。r015 直到禁掉 12% 的对才压到鬼带,代价是
真地板 41% + 墙 78% 陪葬。**这就是签决要求量化的交换比:在 M2 能压鬼的一切工作点上,
墙覆盖的损失都数倍于鬼带收益,且真地板不能幸免。**

## 5. 机制归因

1. **轴向错配(主因)**:鬼壳点生于"对级 ratio 健康、点级三角化角低"的几何(掠射地板:基线
   与深度都正常,视差角却小)。M2 的对级统计量看不见它们 —— r005 禁到的反而是驻留/慢移瞬间
   的对,而那些对生的是墙和物体的覆盖(记忆锚定量坐实)。
2. **对级连坐 + 冗余补偿**:单对被禁时同 site 从其他对照常出生(r002:1,138 禁 → 净 ±1 点);
   要产生净效果必须禁到"该 site 全部对"——即大面积连坐(r015),回到 E9 钝刀的老路。
3. **live 出生是 BA 锚**:禁掉 1% 的对就让窗口 BA 掉进另一收敛枝(r005 p90 282mm)——
   出生口不是可以随便抽积木的地方,E12"出生序=时间序"病理的姊妹现象。

## 6. 肉眼并排(同 gauge 直出,禁 Sim3;`compare_any.html` 相对 exec 目录)

主件(签决交付:原版 vs 改进版 + diff 着色被禁点=红):
- **cap51 OFF vs M2(0.01)**:`compare_any.html?left=E9_birth_alias/runs/cap51_off_r2/replay_finalize.ply&right=E16_m2_lowparallax/runs/cap51_m2/replay_finalize.ply`
- **cap51 diff 着色**(左=OFF 云,红=被禁出生的点;本臂红点 = **0**,即"什么都没被禁"的可视证明):`compare_any.html?left=E16_m2_lowparallax/analysis/cap51_off_r2_diff_vs_m2.ply&right=E16_m2_lowparallax/runs/cap51_m2/replay_finalize.ply`
- **cap50 OFF vs M2(0.01)**:`compare_any.html?left=E9_birth_alias/runs/cap50_off_r2/replay_finalize.ply&right=E16_m2_lowparallax/runs/cap50_m2/replay_finalize.ply`
- **cap50 diff 着色**(红点=0):`compare_any.html?left=E16_m2_lowparallax/analysis/cap50_off_r2_diff_vs_m2.ply&right=E16_m2_lowparallax/runs/cap50_m2/replay_finalize.ply`

敏感性(交换比的肉眼定价;diff 云红=该臂下原位丢失):
- cap51 OFF vs r002:`compare_any.html?left=E9_birth_alias/runs/cap51_off_r2/replay_finalize.ply&right=E16_m2_lowparallax/runs/cap51_m2_r002/replay_finalize.ply`(diff:`…left=E16_m2_lowparallax/analysis/cap51_off_r2_diff_vs_m2_r002.ply&right=E16_m2_lowparallax/runs/cap51_m2_r002/replay_finalize.ply`,红=1 点)
- cap51 OFF vs r005:`compare_any.html?left=E9_birth_alias/runs/cap51_off_r2/replay_finalize.ply&right=E16_m2_lowparallax/runs/cap51_m2_r005/replay_finalize.ply`(diff:`…left=E16_m2_lowparallax/analysis/cap51_off_r2_diff_vs_m2_r005.ply&right=E16_m2_lowparallax/runs/cap51_m2_r005/replay_finalize.ply`,红 24,755——**肉眼看红色集中在墙面**)
- cap51 OFF vs r015:`compare_any.html?left=E9_birth_alias/runs/cap51_off_r2/replay_finalize.ply&right=E16_m2_lowparallax/runs/cap51_m2_r015/replay_finalize.ply`(diff:`…left=E16_m2_lowparallax/analysis/cap51_off_r2_diff_vs_m2_r015.ply&right=E16_m2_lowparallax/runs/cap51_m2_r015/replay_finalize.ply`)
- 横截面速览:`analysis/xsec_e16_cap51.png`(OFF/0.01/0.05/0.15 四联,0.01 与 OFF 同构,
  0.05 现斜向红标糊带,0.15 整体稀疏化)、`analysis/xsec_e16_cap50.png`。
- 臂云均带 NN 真彩(设备生产云取色,>10cm 纯红标):m2 红标 0.32%(cap51)/0.19%(cap50)
  量级 = off 同带;diff 云中设备云不识别的几何为灰。

**不预判取舍——用户肉眼定。** 数据陈述:0.01(签决默认)= 两侧皆零,无取舍存在;
0.05 = 鬼带 −1% 换墙 −65%;0.15 = 鬼带 −81% 换墙 −78% + 真地板 −41% + gauge 碎。

## 7. 诚实边界

1. ON 臂单跑对 off×3 中位;但 cap51 回放近确定性(off×3 逐点互差 ≤±1 点、控制 diff 0.002%),
   m2 的"零效果"是逐点级结论,非统计近似。cap50 的一切带级差异已被 banned=0 机制账本证伪为噪声。
2. r005/r015 的框架读数受位姿翘曲污染(§3 已逐项标注);其可信结论只有 warp-免疫归因(§4)、
   遥测账本与肉眼形态。r015 的 −28.8% 点数与全面稀疏化不受此影响。
3. live 遥测行 20 帧节律,末行 frames=100(共 105 帧)→ live 计数系统性少记 ≤5 帧份额;
   td 行为 finalize 末打印,完整。量级结论不受影响。
4. temporal_detail 的中位深度帧选了 pair 晚帧(frame2),live 选 established 邻帧(prev,
   ORB-SLAM KF2 语义);二者对近邻时间对几乎对称,未做另一侧消融(零咬合结论下无意义)。
5. 0.005 档未烧跑(被 0.01 的 banned=0 子集支配,§2 已证);若未来换采集协议(三脚架/慢扫)
   ratio 分布左移,该结论须重估——M2 的休眠 env 臂留在 E16 exe 里可直接复测。
6. host 墙钟单跑不可信(±30% 纪律);顺带观测:r015 stream 4.0s vs off 5.7s(点少 BA 快),
   仅作量级参考。
7. 本判决证伪的是"对级 baseline/中位深度出生禁令"这一机制;**点级** tri-angle 已有认证定价
   (T15/T20),两者不可互为替身。

## 8. 产物清单(全部本目录,untracked,零 commit)

- `run_e16.sh` + `run_e16_matrix.log`;`runs/cap5{0,1}_m2, cap51_e16exe_envoff, cap51_m2_r{002,005,015}/`
  (manifest 带 binary/input SHA;run.log/err;solved_poses.csv;COLMAP bin;cloud.ply;
  replay_finalize.ply=NN 真彩)
- `smoke/cap51_m2_smoke/`;`e16_vs_e12_copy.diff`(198 行);`SHA256_BINARIES.txt`
- `ratio_diag.py` + `analysis/ratio_distribution.txt`(零咬合物理证据)
- `e16_analysis.py` → `analysis/e16_shell_metrics.json`(壳尺 v2 + raw 法医 + 分面账 + 位姿翘曲
  + diff 账)、`analysis/xsec_e16_cap5{0,1}.png`
- `e16_forensics.py` → `analysis/e16_forensics.json`(warp-免疫分面归因 + 5mm 直方图 + off 噪声带)
- diff 着色云:`analysis/cap5{0,1}_off_r2_diff_vs_m2.ply`、`analysis/cap51_off_r2_diff_vs_m2_r{002,005,015}.ply`
- 编译侧(untracked build 目录):`aether_sfm_c_e12.cc`(含 M2 臂,休眠默认)、
  `libglomap_core_e16.a`、`sfm_replay_bench_e16_exe`、`e16_{compile,link}.log`;
  E12 的 exe/lib/基线 exe 原样未动。
