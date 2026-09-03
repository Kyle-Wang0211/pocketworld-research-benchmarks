# MapAnything 重影根因 + CasDiffMVS 结合（2026-09-03）

用户 09-03 判决：**CasDiffMVS 官方原版 + MapAnything 先验初始化 = 目前最优版本**
（"粘连少了非常多"），先存仓。已知短板：空间完整度不如 MapAnything（CasDiffMVS 只出
中心区域，MapAnything 能出整个房间）。**下一阶段方向（用户定）：最终呈现以 MapAnything
为底，CasDiffMVS 只负责让它没有重影。**

大产物（GLB / PLY / 网页二进制 / 逐视图张量）不进仓，位置见"产物位置"。

## 1. 结论链（全部有数字，见 `records/`）

| 步骤 | 结论 | 记录 |
|---|---|---|
| 官方融合链查证 | 官方无任何融合；维护者 #76 口头推荐 TSDF；#147 承认缺对应损失；论文 Fig.S.5 自认 100 张会重复结构；Hub 无更新权重 | `handoffs/…ADDENDUM…` |
| 逐层归因 | 第一破坏层 = 模型自预测内参：焦距短 23%（比值 0.768），射线误差 6.4°；单视图即错；喂 K 不跟随（0.5×–1.6× 输入 → 输出恒 0.64–0.82），喂 pose 跟随 | `records/layer_audit/`、`records/calib_probe/` |
| 替换归因 | 固定预测深度换真 K/真 pose，官方一致性反而更差（0.29 → 0.63–0.89）：depth/K/pose 共适应 | `layer_attribution.json` |
| 问题 C | exact 基线本就是采集顺序；失败版 D 的变量是**侧躺朝向**（焦距误差 23% → 41%） | `calib_probe/` |
| TSDF（模型自身坐标系） | 7.8 mm 297 万 / 3 mm 1957 万 / 2 mm 4320 万；用户否决（要原生逐像素点云） | `records/tsdf/` |
| 共识深度（不删点） | 逐帧尺度 1.013–1.051；不一致占比 0.291 → 0.193；用户未评 | `records/consensus/` |
| CasDiffMVS 官方原版 | 上游 cd10d5c + 官方 blendmvg + 生产 COLMAP + 官方 10 视图 pair，768×576，官方 filter.py；36.8M 点；**用户：没有任何重影，但白墙粘到行李箱/书包** | `records/casdiffmvs_official/` |
| **结合 v1（当前最优）** | MapAnything 深度逐视图仿射对齐（a≈3.75，有纹理处残差中位 1.1%，覆盖 93%）替换 CasDiffMVS stage-1 初始值，其余全同官方；35.0M 点，存活 0.649 vs 0.671；**用户：粘连少了非常多** | `records/casdiffmvs_prior/` |

## 2. 冻结身份

- MapAnything：`facebookresearch/map-anything` commit `3d10cf7a…`，权重
  `facebook/map-anything-apache` revision `00f9c245…`（Hub 最新），输入 `/root/imgs132_up`
  （manifest `f21362f7…`）。
- CasDiffMVS：`cvg/diffmvs` commit `cd10d5c282a9cabd45a2f64598cd2b990b408d35`（干净克隆；
  研究仓 `tools/python/diffmvs` 的 models/filter.py 带本地提速补丁，**未用**），官方
  `casdiffmvs_blendmvg.ckpt` SHA-256 见 `records/casdiffmvs_official/ckpt.sha256`（含 DTU
  血统，仅测试，不能出货）。
- 输入：`_host_experiments.nosync/pose_ablation_20260818/mvs_P16k`（生产 COLMAP 相机，
  官方 10 视图 pair；`records/casdiffmvs_official/input.sha256`）。
- 🔴 映射铁律：`mvs_P16k/{s}.jpg` 是**源序号**，MapAnything 帧 = `capture_order_source_to_frame[s]`
  （相关 1.0 验过）；upright→landscape = `np.rot90(U, +1)`。

## 3. 脚本（`scripts/`）

- `save_official_outputs.py` 官方 infer 原参复放并落盘全部逐视图张量
- `layer_attribution.py` K/pose/逐帧尺度 + 官方 MV-conf 替换归因
- `calib_follow_probe.py` / `k_follow_synthetic.py` / `rotation_fov_probe.py` 校准跟随与朝向探针
- `tsdf_fuse_mapanything.py` / `tsdf_fuse_gpu.py` Open3D TSDF（CPU / CUDA VoxelBlockGrid）
- `mapanything_consensus_depth.py` 逐帧尺度对齐 + 共识深度（不删点）
- `casdiffmvs_run_official.sh` 官方 CasDiffMVS 原样运行
- `make_prior_maps.py` MapAnything → CasDiffMVS 相机系的逐视图仿射先验
- `casdiffmvs_prior_driver.py` 上游 forward 原样复制 + stage-1 初始值钩子（唯一改动）
- `ply_to_verdict_bins.py` PLY → 网页二进制（逐字节复制）

## 4. 产物位置（不进仓）

- 5090（Vast，临时）：`/root/mapanything_layer_audit_A_imgs132_up_20260903`（1.5 GB 张量）、
  `/root/mapanything_tsdf_fusion_20260903`、`/root/mapanything_consensus_20260903`、
  `/root/casdiffmvs_official_20260903`、`/root/casdiffmvs_prior_20260903`。
- 本机：`progecttwo/_host_experiments.nosync/pose_ablation_20260818/verdict_page/{
  casdiffmvs_official_blendmvg_20260903, casdiffmvs_blendmvg_mapanything_prior_20260903,
  mapanything_consensus_depth_20260903, mapanything_tsdf_gpu_3mm_ownframe_20260903 }`
  （`bin/` 的 SHA-256 在各自 `meta.json`）。

## 5. 下一步（用户 09-03 定向）

最终呈现 = MapAnything 的完整点云；CasDiffMVS 用来消除它的重影。候选做法：以
CasDiffMVS 融合保留像素为锚，把 MapAnything 每帧 log-深度按梯度域/调和偏移场
钉到锚上（保留 MapAnything 的相对形状与全部像素，纠正逐帧尺度与 FOV 引起的
低频畸变），再用生产 COLMAP 相机反投影全部像素。

---

# 第二阶段（同日晚，用户判决驱动）

## 用户判决链
1. **CasDiffMVS 官方原版**：没有任何重影，但白墙粘到行李箱/书包。
2. **结合 v1（MapAnything 深度作 CasDiffMVS stage-1 初始值）**：粘连少了非常多 = 当时最优。
3. 用户定向：**最终呈现必须是 MapAnything**（整间房完整度），CasDiffMVS 只负责消重影。
4. **锚定版**（MapAnything 原生网格 + 平滑偏移场钉到 CasDiffMVS 锚）：重影最少的 MapAnything 版本。
5. **第二刀（只对无锚像素做共识平均）**：比锚定版差。用户原话"你设置的指标就有问题"。

## 🔴 指标事故与真因（本阶段最重要的产出）
官方 `compute_multiview_depth_confidence`（不一致像素占比）**可以被平滑/加噪刷分**：
锚定 0.262 → 第二刀 0.218 → 8 轮迭代 0.180，而用户肉眼顺序正好相反。

我自己的两个假设也被实测推翻：
- "平均会抹掉细节" ⇒ **错**。高频含量反而**上升**（第二刀 1.14×、8 轮 1.49×）：
  最近邻采样把邻居深度混进来，是**加噪点**不是模糊。
- "最近邻造成阶梯量化" ⇒ **错**。相邻像素零差分占比 0.0，7×7 窗内 49 个值全不同。

**真因（已定罪）**：第二刀**只对无锚像素**平均、锚像素不动，而 CasDiffMVS 锚掩膜是斑块状的
⇒ 沿掩膜边界产生深度台阶。跨边界/区域内相对跳变 = **3.65**（锚定 1.29、8 轮 1.13），
每帧约 8000 对边界像素、0.6% 相对深度（4.5 m 处 ≈ 2.7 cm），白墙上就是斑块状分层。

⇒ **通则：任何处理都不要只作用于像素的一个硬子集**（掩膜/置信度门/区域），
边界必成缺陷；要么全图作用、要么平滑权重、要么把证据放进平滑参数场。

## 三把尺子（已用用户判决校准，`scripts/three_rulers.py`）
| 尺子 | 抓什么 |
|---|---|
| SEAM | 跨锚掩膜边界 / 区域内相邻深度跳变比 —— 抓"只改子集" |
| LAYERS | 伙伴视图在同一像素沉积的第二表面（间隔 > max(2cm, 1%z)、质量 ≥ 15%）占比 —— 真重影 |
| DETAIL | 相对参照版的 \|z − blur(z)\|/z 比 —— 抓加噪与抹平 |

| 版本 | SEAM | LAYERS | DETAIL | 用户 |
|---|---|---|---|---|
| 锚定 | 1.175 | 0.7162 | 1.0000 | 最优（当时） |
| 第二刀 | **3.650** | 0.6123 | 1.1418 | 更差 |
| 8 轮迭代 | 1.109 | 0.2523 | **1.4879** | 未呈现（已判死） |
| **联合平滑场** | **1.170** | **0.6250** | **1.0023** | 待定 |

**只有三项都不退步、LAYERS 下降的候选才值得占用用户的眼睛。**

## 联合平滑场（当前候选，`strengthen-consistency-via-smooth-field`）
与锚定版唯一区别：无锚区的跨视图一致性证据也进入**平滑偏移场的数据项**，
而不是进深度图。逐像素深度关系一个都没改，所以表面洁净度不可能变。
对照臂 `--w_cross 0` 复现锚定版且各轮不再变化，证明跨视图项是唯一活动变量。
官方一致性 0.259 → 0.221（仅用于定位）；场内跨度 5.2%；点数不变 25,150,854。

## 本阶段新增脚本
`export_native_anchored.py`（原生网格导出，修掉 0.75 步长条纹）、
`anchor_mapanything_to_casdiff.py`、`consensus_on_anchorfree.py`（已判死）、
`iterative_consensus_anchored.py`（已判死）、`joint_consistency_solve.py`（低阶联合，0.305 太刚）、
`joint_smooth_field.py`（当前候选）、`ghost_ruler.py` / `seam_test.py` / `three_rulers.py`（尺子）。
