# colmap PR #4354 重三角化加速 cherry-pick — 实验报告

**日期**:2026-07-05(通宵提速战役第 4 件)
**结论**:✅ **采纳入树**(Aether3D 主仓 `claude/publish-to-community` commit `b0133902`)。9/9 质量门 PASS,reproj 中位与认证基线一字不差,user 真彩 viewer 肉眼复核通过。

## 上游信息

- PR:colmap/colmap **#4354** "Simplify merge_trials_ and reuse Complete() BFS allocations in IncrementalTriangulator"(ahojnnes)
- Merge commit:`56b9dfa679835712d07643cea87cbce675f0db33`
- 语义等价背书:关联 PR #3967 的行为级单测(CompleteImage/MergeTracks/Retriangulate 等)**已存在于我们 vendored 4.0.4 的 `incremental_triangulator_test.cc`**,#4354 零改动测试文件 = 上游以"旧测试原样通过"验证行为不变。

## 改动内容(vendored colmap-src,4 文件零冲突)

1. `sfm/incremental_triangulator.cc/.h`:`merge_trials_` 扁平化(`unordered_map<pt,set<pt>>` → `unordered_set<pair>` canonical (min,max) 键);Complete() BFS 队列改成员级 scratch buffer 复用 + `(image_id, point2D_idx)` visited 去重。
2. `util/types.h`:新增 `std::hash<std::pair<u64,u64>>` 特化。
3. `util/types_test.cc`:上游 verbatim 单测(我们构建排除 _test,不参与编译)。
4. 全部改动带 `[AETHER] cherry-picked from upstream colmap PR #4354` 标记;未触碰任何既有 [AETHER] 补丁。

## 验证(host,dense-414 全场景 + sub150 选区,同夜背靠背,Mac 独占零编译污染)

### 9 指标门(vs 认证基线,SV 用噪声带锚 ≤0.0630,其余 3%)

| 指标 | 基线 | C4354 | 判 |
|---|---|---|---|
| reproj中位 | 1.0292 | **1.0292** | ✓ 一字不差 |
| 表面变差 | 0.0604 | 0.0626 | ✓(噪声带内) |
| 三角化角 | 11.3842 | 11.3789 | ✓ |
| 弱track% | 3.9805 | 3.9501 | ✓ 略好 |
| 球拟合 | 0.0507 | 0.0506 | ✓ |
| 地板厚度 | 0.0020 | 0.0020 | ✓ |
| ARKit位置mm | 9.4792 | 9.4592 | ✓ 略好 |
| ARKit方向° | 0.6057 | 0.6071 | ✓ |
| 点数 | 204,445 | 204,326(−0.06%) | ✓ |

**[C4354] PASS 全指标。**

### 计时(单跑,host wall 方差 ±30% 已知,标注为参考值;采纳决策不依赖计时)

| 场景 | 同夜对照(旧二进制) | #4354 | Δ |
|---|---|---|---|
| 全场景 414f | 25.4 min(solve 1148.7s + ba 375.0s) | 22.0 min(solve 1019.3s + ba 302.5s) | −13% |
| 选区 150f | 69.8s | 67.0s | −4% |

### 肉眼复核

真彩点云(ARKit 系对齐,NN 中位距 0.000195 同系确认;颜色从认证真彩云同源移植)挂入 `tiled_414_viewer/viewer_ab.html` 键 k,与认证云(键 p)同坐标系原地切换 —— **user 裁决:肉眼检查没问题**。

## 同夜战役上下文(其余三件)

- SPSE 预条件子(AETHER_SPSE):☠️ 判死 —— 干净环境 82.4min vs 对照 25.4min(慢 3.2×,单核病理)+ ARKit位置挂门;代码留 debug opt-in 已标 REJECTED。
- faiss 审计:✅ 关账 —— 不在关键路径(vendored build 显式 brute-force 为流式设计;fixture 匹配本就是 pycolmap faiss 跑的;生产 iOS 是自研 Metal matcher)。
- track 预算(AETHER_MAX_TRACKS):⏸️ 悬案 —— 弱track% 剂量效应真实(83k→4.55 / 124k→4.14 / 160k→4.00,门 4.10);全场景单跑计时非单调不可判(host 方差);ARKit位置疑似 SV 式噪声带(同夜五跑含对照 span 9.54-9.99,门 9.76 在带中间),家族复核(C×4+T160×4 交错)进行中。
