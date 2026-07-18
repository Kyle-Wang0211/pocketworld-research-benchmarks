# DR1 · RealityScan 桌面版 Mac 核实 + 默认参数表 VERIFIED 升级(2026-07-18)

## TL;DR

1. **RealityScan 2.x 桌面版没有 macOS 版,从来只有 Windows(+Linux 仅 CLI)。** "Mac 装 RealityScan 2.x 抄默认面板"这条 R1-TODO 路线**不存在**,诚实报废。
2. 但替代路径**全额兑现且超额**:官方 **Keys and Values 键值表**(rshelp.capturingreality.com,一手直连抓取)就是"默认面板"的机器可读形态——**全部对齐默认参数一次性升 VERIFIED**,含 R1 表里全部 7 项 SUPPORTED、2 项 INFERENCE、2 项 UNRESOLVED。
3. 全量默认表(App/Alignment/Reconstruction/Texture/Error,101 行)见 `defaults_table_full.md`;原始证据+SHA256 在 `evidence/`。
4. 实机 UI 抄面板从"必做校准"降级为"可选交叉验证",需要一台 Windows 机器,清单见 §5。

---

## ① OS 支持核实(结论:Windows-only,无 macOS)

| 证据 | 内容 | 抓取方式 |
|---|---|---|
| realityscan.com/download(官方) | 桌面版系统需求:"Windows 8 / 8.1 / 10 / 11 64-bit or Windows Server version 2008+, 8 GB RAM, NVIDIA graphics card with CUDA 3.5 capabilities and 1 GB VRAM";页面唯一的 "Mac" 字样属于 **Epic Games Launcher**(Launcher 有 .dmg,RealityScan 本体没有) | 一手 curl,`evidence/realityscan_com_download.html` |
| dev.epicgames.com 官方 docs "Hardware and Software Requirements" | "RealityScan runs primarily on **Windows**. A **Linux version** is also available, but it is recommended **only for CLI-based workflows**."——OS 清单里根本没有 macOS 条目 | 经 r.jina.ai 代理(本网络对 dev.epicgames.com TLS 层掐断,TCP 443 通、HTTPS 超时;代理内容与直连搜索索引一致),`evidence/devepic_hw_software_requirements_via_jina.md` |
| dev.epicgames.com 知识库 DB58(2026-07 现行) | "a 64-bit version of **Windows 10, Windows 11, or Windows Server 2016 or newer**";CPU 须 AVX2;NVIDIA CUDA 3.5+(无 N 卡可跑注册/对齐,但不能建模/出纹理) | 同上代理,`evidence/devepic_kb_DB58_hw_os_requirements_via_jina.md` |
| CG Channel 2026-06-25(二手核对) | RealityScan **2.2**(当前最新):Windows 10+/Server 2016+,Linux CLI(Ubuntu 24.04/Fedora 39);全文无 macOS | WebFetch |
| Wikipedia RealityCapture(二手核对) | OS 栏 = "Microsoft Windows",无 macOS | WebFetch |

- 版本线:RealityCapture 1.x → 2025-06 更名 RealityScan 2.0 → 2025-11 2.1 → 2026-06-25 **2.2**(加 AMD GPU 加速,仍 Windows)。任何版本都没出过 macOS 桌面版。
- Linux 版仅推荐 CLI(2.1 起经打包 Wine 跑),不是 GUI 抄面板路径。
- 老知识库/第三方 FAQ 提过 "Mac 用 Boot Camp 装"——Boot Camp 仅 Intel Mac,对 Apple Silicon 不适用,不构成 Mac 路径。

**判定:R1 的"装 Mac 版 RealityScan"前提不成立(信息有误),走 ③ 替代路径。**

## ② 官方下载渠道(供有 Windows 机器时用)

- 桌面版**只经 Epic Games Launcher 分发**(免费,年收入 <$100 万免 license;超出 $1,250/席/年),**无免登录的 RealityScan 独立安装包直链** → `downloads/` 目录留空,无文件可报 SHA。
- Epic Games **Launcher** 安装器官方直链(从 realityscan.com/download 页内提取,记录在案;Launcher 本身无需登录即可下载,登录发生在 Launcher 内):
  - Windows:`https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.exe?productName=unrealEngine`
  - macOS:`https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncher.dmg?productName=unrealEngine`(⚠️Mac Launcher 里**没有** RealityScan 条目——RealityScan 无 macOS 二进制,装了 Launcher 也装不了)

## ③ 替代路径执行结果:参数表升级账

替代路径 = 官方在线帮助的 **Keys and Values 全设置键值表**(`set`/`preset` 命令的键值全清单,**含 Default 列** = UI 默认面板逐项数值)。R1 当时没发现这张表(rshelp 站点 TOC 里的 `tutorials/setkeyvaluetable.htm`),它正是"抄默认面板"要抄的东西,而且是官方机器可读版。

**双源交叉:**一手直连 rshelp.capturingreality.com(无代理,SHA 落盘)× dev.epicgames.com 新 docs(代理)——**Alignment 段核心参数 100% 一致**;另有官方 KB DB58 独立句子 "Reducing feature count per image from the default (e.g., 40,000)" 三方互证 40k。

### 升 VERIFIED 的参数(R1 表 → 现状)

| 参数 | 默认值(官方) | R1 原证据级 | 现证据级 |
|---|---|---|---|
| Max features per image | **40,000**(`sfmMaxFeaturesPerImage`) | SUPPORTED | **VERIFIED**(键值表一手 + DB58 明文双证) |
| Max features per mpx | **10,000**(`sfmMaxFeaturesPerMpx`) | SUPPORTED | **VERIFIED** |
| Preselector features | **10,000**(`sfmPreselectorFeatures`) | SUPPORTED | **VERIFIED** |
| Detector sensitivity | **Medium**(`sfmDetectorSensitivity`,取值 Low/Medium/High/Ultra) | SUPPORTED | **VERIFIED**(与论坛 admin "MEDIUM is the best case scenario" 互证) |
| Max feature reprojection error | **2.0 px**(`sfmMaxFeatureReprojectionError`) | SUPPORTED | **VERIFIED**(官方推荐 ≤3px 不变) |
| Image overlap | **Medium**(`sfmImagesOverlap`) | SUPPORTED | **VERIFIED** |
| Image downscale factor | **1**(`sfmImageDownscaleFactor`) | UNRESOLVED-矛盾 | **VERIFIED,矛盾解除**:社区"默认 3"确系与**深度图**降采样混淆(官方:depth-map Preview=4、Normal=2,对齐=1) |
| Feature detection quality | **High**(`sfmFeatureDetectionQuality`,取值 High/Normal) | UNRESOLVED | **VERIFIED** |
| Force component rematch | **false**(`sfmForceComponentRematch`) | INFERENCE | **VERIFIED** |
| Draft: Final model optimization | **false**(`sfmFinalModelOptimizationDraftMode`;draft 降采样=2、overlap=Medium) | UNRESOLVED | **VERIFIED**(draft 默认**不做** final BA,印证"draft=显式降质档") |
| Add recon region after alignment | **true**(`sfmAutoReconRegionAfterAlignment`) | (未列) | **VERIFIED**(新增) |
| Distortion model | **Brown3**(`sfmDistortionModel`) | (未列) | **VERIFIED**(新增) |
| Camera priors | 启用=**true**;位置精度 X/Y=10.0、Z=20.0;硬度=1.0;Yaw/Pitch/Roll=10.0;朝向硬度=1.0 | (未列) | **VERIFIED**(新增;对我们"ARKit 先验"对标有直接价值) |

重建/纹理段同表全量 VERIFIED(节选):depth-map downscale Preview=**4**/Normal=**2**、mesh 平滑权重 **1.5**、`mvsPreviewMeshStrategy`=**sfm(用稀疏云)**、unwrap 最大纹理 **8192**、texturing 前不降采样(**1**)/coloring 降采样 **2**、Coloring/Texturing style=**VisibilityBased**。全表见 `defaults_table_full.md`。

### 仍非 VERIFIED 的残项

| 项 | 状态 | 说明 |
|---|---|---|
| "Merge components only" 默认 | SUPPORTED(结构性) | 键值表**无此持久设置**;它是对齐动作的显式选项/`mergeComponents` 命令,不触发即不生效,与 R1 推断"默认 No"一致 |
| 1.x 旧默认(20,000 特征等) | SUPPORTED(历史) | 仅史料价值,不影响复刻(抄现行值) |
| 键值表 ↔ 当前 2.2 安装包逐位一致性 | SUPPORTED | 在线帮助为现行文档,但无法在本机装包实证;此为 §5 可选实机校验的唯一残余价值 |
| 两官方源漂移:`sfmControPointImageMeasAccuracy`(rshelp 2.0 vs dev.epicgames 4.0)、`sfmDefinedDistanceAccuracy`(0.10 vs 0.001) | 记录在案 | 仅 GCP/控制点工作流用,与我们复刻无关 |
| RS mobile 内部机制 | **UNRESOLVED🔴红线不变** | 本文全部为桌面版;不据此声称 mobile 内部任何行为 |

## ⑤ 用户需做的最后一步(可选,非阻塞)

参数表已全 VERIFIED,以下仅为"实机 UI 面板 ↔ 文档键值表"的最终交叉验证(30 分钟),需要 Windows 环境 + Epic 账号登录(只能用户做):

1. 找一台 **Windows 10/11 64-bit** 机器(CPU 需 AVX2;**不需要 NVIDIA GPU**——查看设置面板与跑对齐不需要 CUDA,只是不能建模/纹理)。
2. 下载 Epic Games Launcher(上面 Windows 直链或 store.epicgames.com),安装后**登录 Epic 账号**。
3. Launcher → Unreal Engine 区 → RealityScan → Install(免费,收入 <$100 万)。
4. 打开 RealityScan → ALIGNMENT tab → Registration → **Alignment Settings**,逐项与 `defaults_table_full.md` Alignment 段对照并截屏(重点:40,000 / 10,000 / Medium / 1 / 2.0 / High / Medium / 10,000)。
5. 顺手截 MESH & COLOR → Create Mesh / Color & Texture 两个面板,对照 Reconstruction/Texture 段。
6. 没有 Windows 实体机的备选(均未实测,UNTESTED):Apple Silicon + VMware Fusion(免费)+ Windows 11 ARM **24H2**(Prism 支持 AVX2 仿真,理论可跑注册与看面板)/ 云 Windows GPU 实例。**不要**为此买硬件——此步价值仅剩"在线帮助与装机版本逐位一致"的确认。

## Evidence 清单

`evidence/SHA256SUMS.txt` 有全部哈希。关键件:

- `tutorials_setkeyvaluetable.htm` — **官方键值表一手抓取**(SHA256=1396…e455),本次升级的核心证据
- `devepic_keys_and_values_via_jina.md` / `devepic_hw_software_requirements_via_jina.md` / `devepic_kb_DB58_hw_os_requirements_via_jina.md` — dev.epicgames.com 官方 docs/KB(代理抓取,交叉源)
- `realityscan_com_download.html` — 官方下载页一手(OS 需求 + Launcher 直链)
- `appbasics_*.htm` / `tutorials_draftalign.htm` / `allcommands.txt` 等 — R1 期一手抓的官方帮助页(本次沿用)

网络备注:本网络对 dev.epicgames.com 为 TLS/SNI 层掐断(TCP 443 通、TLS 超时),直连不可达;rshelp.capturingreality.com、realityscan.com、forums.unrealengine.com 均直连正常——故一手核心证据落在 rshelp,dev.epicgames 内容经代理并与搜索索引/一手表交叉核对。
