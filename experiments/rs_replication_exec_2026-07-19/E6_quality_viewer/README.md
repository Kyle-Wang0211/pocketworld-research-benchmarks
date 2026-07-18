# E6-B · S4 显示层原型:RS 式 quality 重着色 viewer(display-only)

日期:2026-07-18 · 机器产物,研究 viewer 原型,**不进生产、不 commit**(编排者统一提交)。

## 是什么

`compare_quality.html` = `../compare_any.html` 的扩展副本(基础功能逐字保留:同 gauge 双栏、四预设视角、双栏同步相机),新增 **color / quality 双模式切换**,复刻 RS 已证预览行为(E2-C/R1):

| RS 已证行为 | 本原型对应 |
|---|---|
| 同一片云可 color/quality 切换 | HUD `color`/`quality` 按钮 + 键盘 `c`/`q`,双栏同步切换 |
| quality = 覆盖热图,绿(高)→红(低) | 每点局部支持度映射 红#e03a2a→黄#e0b02a→绿#2ae03a |
| percentile 70 定色标锚 | score ≥ p70 → 纯绿;score=0 → 纯红;每云独立 p70 锚(与 RS 每云自适应色标一致) |
| **全量重着色,非过滤** | 100% 点参与重着色,零点被隐藏/删除;点数计数两模式恒等 |

## 用法

```bash
# 在 repo 根(pocketworld-repro-contract-20260714)起服务
python3.11 -m http.server 8129
open "http://localhost:8129/experiments/rs_replication_exec_2026-07-19/E6_quality_viewer/compare_quality.html?left=../../../data/pocketworld_captures/cap50/device_full_pull_2026-07-17/sfm_sparse.ply&right=../E3_birth_discipline/cap50/e3_candidate_cap50.ply"
# 可选参数:&mode=quality 直接进 quality 模式;&view=top 指定初始视角;&llabel=/&rlabel= 自定义标签
```

## display-only 铁证

- 本页对 PLY 只有 `fetch` 读取路径;quality 颜色仅存在于内存 `Float32Array` 与 WebGL 顶点缓冲(每 pane 两套颜色 buffer,切模式只换 attribute 绑定)。无任何写文件/上传代码路径。
- 渲染前后输入 PLY SHA256 复核一致(`shasum -c` OK):
  - `sfm_sparse.ply`(cap50 生产云,92,849 点):`a41bd10f9d5832f9f98bbbaf8d566890d21d2bffa7d3142da27db0bfdb8f36df`
  - `e3_candidate_cap50.ply`(S1+E3 组合候选,92,132 点,用户已批):`b69af4a1106c940a6d6cec7f43cf2e9488363ef8bb92d9c7feba8e8bceac7ebf`
- 质量无损:位置/原色/点数全量不动,重着色是纯显示层视图。

## ⚠️ 诚实声明:我们缺 nviews 字段(quality 目前是密度代理)

- **生产 PLY 头只有 x/y/z + RGB**(已实测两输入头),没有 nviews/support/track_len 任何逐点支持度字段。
- RS 的 quality 语义是每点真实观测支持度(覆盖热图);本原型退而用**k 近邻密度代理**:半径 r = 场景最大边/64 的球内邻居计数(均匀网格哈希 O(n)),本次 cap50 实测 p70 锚:左 2020 / 右 2001 邻居。
- 密度代理与 nviews 相关但不等价(高密度区可以由少数帧贡献)。**真 quality 模式需要交付层 PLY 带逐点 nviews/support 字段 = 生产管线改动,须用户签决**,不在本原型范围。
- 若未来 PLY 带上述字段,本页已内置探测:`nviews`/`support`/`track_len` 任一存在即自动改用真字段并在 HUD 声明(代码 `parsePLY` 的 `qProp` + `buildQualityColors`)。

## 验证渲染(cap50 生产云 vs e3 候选,overview 视角,headless Chrome 1600×900)

- `screenshot_color_cap50.png` — color 模式:双栏真彩,Δ点数 -717 (-0.77%)。
- `screenshot_quality_cap50.png` — quality 模式:双栏同步重着色,绿=高支持核心区(桌面/密集面),红=低支持外缘与飞散点;两栏点数与 color 模式恒等(全量重着色非过滤);右下角图例含 p70 锚标注。

## 产物清单 + SHA256

| 文件 | SHA256 |
|---|---|
| compare_quality.html | 见 SHA256SUMS.txt |
| screenshot_color_cap50.png | 见 SHA256SUMS.txt |
| screenshot_quality_cap50.png | 见 SHA256SUMS.txt |

（SHA256SUMS.txt 由生成脚本落盘,README 本文件不含自身 SHA。）
