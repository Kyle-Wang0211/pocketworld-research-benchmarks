# E17 终审 — L2 渲染门作为预览鬼层治理的即用件

日期 2026-07-18(实验计划标 07-19)。战场=预览(用户锁死)。display-only 铁律:交付 PLY 永远全量,本实验只产"预览视效"对比件。

## 1. 规则与装机开关定论(71935a5 vs Q8 矛盾 → 已澄清)

**确切规则**(lib/capture/ghost_view_filter.dart,逐字):
- `hidden = band15 ∧ ¬rescued` ⇔ `visible = ¬band15 ∨ rescued`
- band15 = bit1 = `kGhostHideBits`(header 唯一 display gate 位);rescued = bit5(L1 CasDiffMVS 仲裁"真面"白名单);cell_ghost/band10/in_region/in_clean 是仲裁/参考位,渲染门**不消费**。
- 无 obs 依赖:2-view 好点全放行(旧「obs≥3∨rescued」腿已按签决删除)。

**装机开关状态 = 默认开(ON),Q8"默认关"是错的**:
- `kGhostMaskViewFilter = bool.fromEnvironment('PW_GHOST_VIEW_FILTER', defaultValue: true)`(ghost_view_filter.dart:56-59)。
- 71935a5(「默认开门(用户签决)」)在当前 ar-capture-rs 分支历史上(HEAD~3 可见);repo 内 grep 无任何 build 脚本/xcconfig/plist 覆写 `PW_GHOST_VIEW_FILTER`。
- 消费方两处、都受此开关控:采集预览 `ar_capture_page.dart:1478`、草稿查看页 `sparse_cloud_viewer_page.dart:121`。
- **Q8 矛盾根源 = 过期注释**:`ar_capture_page.dart:1427`"kGhostMaskViewFilter=false(默认)时只出遥测"是 71935a5 之前的旧注释没跟着改;`sfm_live_recon.dart` 附近注释同期。代码行为以常量为准 = 开门。⚠️建议顺手清这两句陈旧注释(本实验不改生产)。

## 2. Mask 对齐(E2-A 疑虑收口)

E2-A 的 93,360(裁前)vs 92,849(交付)错位只存在于 native `ghost_mask.bin`(Points3D 序)。**交付点序 sidecar `ghost_view_mask.bin` 与交付 PLY 逐位对齐**(cap50: 92,849 == PLY;cap51: 64,392 == PLY),本实验直接消费它,无需借 E9 回放云。自洽证据:band15 native→view 6013→6002 / 4927→4922(差值恰为过滤删点),bit5 rescued 719/468-469 已流入交付序(BIT5-FIX 在这两库真实生效过)。

## 3. 量化(认证平面直尺 = ghost_mask.json 的 plane_n/plane_d,生产自产)

| 指标 | cap50 | cap51 |
|---|---|---|
| 交付点数 | 92,849 | 64,392 |
| band15(交付序) | 6,002 | 4,922 |
| rescued(bit5)放行 | 719 | 468 |
| **hidden = band15∧¬rescued** | **5,283(5.69%)** | **4,454(6.92%)** |
| band15 内实际隐藏比 | 88.0% | 90.5% |
| 地板下鬼带(sd<−1.5cm)**足印区内**藏比 | 43.3%(2189/5050) | **99.2%(3654/3684)** |
| 地板下鬼带**全云**藏比 | 38.3% | 50.8%(区外 3,503 点不受治) |
| 第二片(+1.5~5cm 区内)藏比 | 78.0%(2078/2664) | 29.3% |
| 误藏(hidden 且 \|sd\|≤1.5cm) | 647(其中 278 在 1.0-1.5cm 带缘) | 395(342 在带缘) |
| **核心误藏(\|sd\|<1cm)** | **369 = hidden 的 7.0% / 全云 0.40%** | **53 = 1.2% / 0.08%** |
| native 侧 pass 耗时 | 30ms | 29ms |

hidden 的 sd 分布(cm):cap50 双峰 = 地板下 −5~−8(1,655 点,深层镜像片 **0 漏标**)+ 地板上 +1.5~+5 第二片(2,078 点,恰是 47 号双层地板病理);cap51 单峰 = −1.5~−8 镜像鬼带(3,654 点)。

## 4. 肉眼对比(同 gauge 真彩直出,禁 Sim3)

- `compare_any.html?left=E17_l2_preview_sim/cap50_full_off.ply&right=E17_l2_preview_sim/cap50_l2on_preview.ply`
- `compare_any.html?left=E17_l2_preview_sim/cap51_full_off.ply&right=E17_l2_preview_sim/cap51_l2on_preview.ply`
- 静态:`cap50_full_vs_l2on.png` / `cap51_full_vs_l2on.png`(俯视/立面/横截面)。

肉眼读图:cap51 立面里 −3~−5cm 鬼带在足印区(x≈0.6~2.5m)**整段消失**,但 x<0.6m(足印区外)残带原样留存,藏区边界有清晰台阶;cap50 深层 −7~−8cm 镜像块基本消失、第二片大半消失,但右侧 −2~−3cm 浅裙(未被 band15 标记)残留可见。俯视图两库几乎无差(藏的点集中在地板带,不动结构)。

## 5. 终审

**效果几成?——足印区内约八成,全云约六成。** cap51 是标杆案例(区内 99.2% 歼灭、误藏核心 0.08%);cap50 揭示两个真实残留:①band15 只在足印 cell 内定义,**足印区外的地板下鬼完全不受治**(cap51 全云藏比被拖到 50.8%,肉眼可见残带+台阶边界);②cap50 的 −1.5~−3cm 浅噪声裙 2,861 点未被标(band15 标的是确证簇,浅裙属低视差噪声壳,设计上就不在"确证鬼"内)。

**误藏几何?——核心误藏 0.08%~0.40%(53/369 点),带缘另有 ~300 点。** rescued 白名单真实在工作(719/468 点放行,放行点中位数在 +1.8cm ≈ 踢脚/台阶高度)。⚠️诚实边界:平面直尺只能证"这些点离认证地板 <1cm",无 dense truth 无法裁定它们是真地板还是恰好贴地的鬼簇成员;"误杀=0 红线"在 display-only 语义下不触(数据全量,只是预览不显示)。

**装机只差什么?——什么都不差,已经装上且默认开。** 71935a5 起两个预览 surface(采集预览+草稿查看页)默认消费渲染门;native 出 mask 需 `AETHER_GHOST_MASK=1`(cap50/51 盘上有 mask = 该路径当时是活的,装机包是否常开此 env 未在本实验范围内核验——若不开则无 sidecar、容错全显示)。要把 E17 视效变成更彻底的鬼层消失,差的不是开关,是**上游覆盖**:(a) band15 扩展到足印区外的地板下点;(b) 浅裙(−1.5~−3cm)治理——这属于 M2 低视差/E16 战线,不是 L2 的锅。另建议清 ar_capture_page.dart:1427 等两处过期注释(Q8 误判的源头)。

## 6. 产物 SHA256

见同目录 `SHA256SUMS.txt`;指标 `e17_metrics.json`、`e17_band_coverage.json`;脚本 `e17_l2_sim.py`、`e17_render.py` 可复跑(python3.11)。
