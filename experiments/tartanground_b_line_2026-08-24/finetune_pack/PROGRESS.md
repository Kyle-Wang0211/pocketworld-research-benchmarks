# TG 白墙子集微调弹药包 — 进度(增量写,防中断丢工作)

日期:2026-08-24 起。产物根目录:`/Users/kaidongwang/Developer/tartanground_b_line/finetune_pack/`

## 已确认的既有材料(逐条查过)

| 材料 | 绝对路径 | 状态 |
|---|---|---|
| TG→BlendedMVS 训练格式转换器 | `/Users/kaidongwang/Developer/tartanground_b_line/tartanground2mvsnet.py` | 已读完全文;帧选择只支持 `--stride/--max_frames`,**需加按帧号列表选帧的入口** |
| Office P0000 全套 | `/Users/kaidongwang/Developer/tartanground_b_line/raw_download/unzipped/{image,depth}/…_lcam_front` + `metadata/pose_lcam_front.txt` | image 678 张 / depth 678 张,齐 |
| step0 逐帧纹理分数 | `step0/res_TG_{Office,House,Hospital,…}.json` | 每档只有 **250 帧等距抽样**(Office 轨迹 678 帧、House 356 帧),**不是全帧** |
| 纹理度量脚本 | `step0/lowtex.py` | THR=100 / 短边 640 / Sobel3+box5,可直接复用 |
| 官方训练入口 | `…/tools/python/diffmvs/{train.py,datasets/blend.py,scripts/train/train_casdiffmvs.sh}` | 已读完 |
| 续训起点 ckpt | `/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/casdiffmvs_mvgZeroDTU.ckpt` | `ls -lO` 无 dataless,11,766,857 B,可读 |

## 关键结论(边做边记)

1. **混数据不用改一行网络代码。** `datasets/blend.py::MVSDataset` 只吃 `(datapath, listfile)`:
   listfile 每行一个 scan 名,scan 目录挂在 `datapath` 下。所以把 TG scan **软链**进
   BlendedMVG 根目录、并把 scan 名追加进 train.txt 即可。混合比例 = **同一个 TG scan 名在
   train.txt 里重复几次**(`build_list()` 逐行处理,重复行 = 重复 metas)。完全照抄官方
   `train.py` 调用方式。

2. **🔴 分辨率必须与 BlendedMVG 对齐。** `blend.py` 全程不 resize,`DataLoader(batch_size=4)`
   默认 collate 要求同 batch 内张量同形状。TG 原生 640×640 与 BlendedMVS/MVG 的 768×576
   不同 ⇒ 混在一个 batch 会直接崩。转换器必须输出与 BlendedMVG 一致的尺寸。
   本包做法:640×640 **中心裁到 640×480(4:3,与 768×576 同宽高比)→ 各向同性缩放 1.2×
   到 768×576**,内参同步变换(cy 减裁剪偏移,fx/fy/cx/cy 同乘 1.2)。目标尺寸做成参数
   `--out_w/--out_h`,租用机上先量 BlendedMVG 真实尺寸再定。

3. **`trainviews=9` ⇒ pair.txt 每个 ref 至少要有 8 个 src**,否则 `build_list()` 直接丢弃
   该 ref(`less ref_view small 8`)。转换器 `--num_src` 必须 ≥ 8,且要核对实际非零对数。

4. **续训起点的血统**:`casdiffmvs_mvgZeroDTU.ckpt` = 零 DTU + BlendedMVG 32 轮,
   100% 复刻官方 `train_casdiffmvs.sh` 第②③段(唯一变量 trainpath/trainlist)。
   ⇒ 本次续训的粮食基底应是 **BlendedMVG**(不是 BlendedMVS 子集)。

## 实验设计(用户拍板,2026-08-25)

| 臂 | 内容 | 卡时 | 状态 |
|---|---|---|---|
| **B(主实验,唯一要训)** | mvgZeroDTU 续训,BlendedMVG + TG 白墙帧 20%,epochs=4 | 1 份 | 弹药已备齐 |
| 对照 | 现有 `mvgZeroDTU.ckpt` 原样 | **0** | 只需跑验收链 |
| A(条件臂) | 同样本量同轮数、**不掺 TG** 的续训 | 1 份 | **只在 B 有真增益时才补跑**(RUNBOOK 7.5) |
| C(Prism 式蒸馏) | **本次不做** | 0 | 配方存 RUNBOOK 附录 D |

## 步骤进度

- [x] **步骤 1 补齐数据** — 见下节
- [x] **步骤 2 白墙帧筛选**
- [x] **步骤 3 转换 + 官方 dataloader 抽验**
- [x] **步骤 4 训练配方脚本**
- [x] **步骤 5 验收脚本(一键 ckpt→数字)**
- [x] **步骤 6 RENTED_MACHINE_RUNBOOK.md**

### 步骤 1:补齐数据

数据源确认:HF dataset repo `theairlabcmu/TartanGround`
(出处 `tartanairpy/tartanair/downloader.py:148-149`)。已用 `HfApi.list_repo_files` 核实
`House/Data_omni/P000{0,1,2}/…` 与 `Office/Data_omni/P000{0..4}/…` 均存在。

下载脚本:`finetune_pack/download_tg.py`(hf_hub_download 断点续传 + 与 repo 侧 size
逐字节核对 + 失败重试 6 次)。后台运行,日志 `finetune_pack/download.log`。

清单(12 个文件,合计 2.068 GB,远低于 10 GB 预算):
- House P0000/P0001/P0002 × {image,depth}_lcam_front.zip + metadata.zip
- Office P0001 × {image,depth}_lcam_front.zip + metadata.zip

Hospital 按任务要求不下。**已全部完成:12/12,逐字节核对通过(`[done] ok=12 bad=0`)。**

解压后逐条核对(image/depth/pose 三者帧数必须相等):

| 轨迹 | image | depth | pose 行数 |
|---|---|---|---|
| Office P0000(旧下载) | 678 | 678 | 678 |
| Office P0001 | 1072 | 1072 | 1072 |
| House P0000 | 356 | 356 | 356 |
| House P0001 | 470 | 470 | 470 |
| House P0002 | 1323 | 1323 | 1323 |

### 步骤 2:白墙帧筛选

step0 的 res_*.json 只有 250 帧等距抽样,不够选帧用,因此**用同一把尺子
(`step0/lowtex.py`,THR=100/短边640/`--n -1` 全帧)重跑**,产物
`finetune_pack/tex_TG_*.json`。筛选脚本 `finetune_pack/select_frames.py`。

全轨迹纹理分布(f100 = 低纹理像素占比):

| 轨迹 | 帧数 | f100 中位 | 平均灰度中位 |
|---|---|---|---|
| Office P0000 | 678 | **0.617** | 193.4 |
| Office P0001 | 1072 | **0.488** | 152.2 |
| House P0000 | 356 | 0.468 | 56.9 |
| House P0001 | 470 | 0.450 | 49.2 |
| House P0002 | 1323 | (见 selection.json) | — |

筛选结果(Office: f100>0.4;House: 先 mean_gray>=90 再 f100>0.4):

| 轨迹 | 全帧 | 过 f100 | 过亮度 | 最终入选 | 切块后进训练集 | scan 数 |
|---|---|---|---|---|---|---|
| Office P0000 | 678 | 605 | — | **605** | 586 | 6 |
| Office P0001 | 1072 | 888 | — | **888** | 884 | 10 |
| House P0000 | 356 | 238 | 80 | **68** | 65 | 2 |
| House P0001 | 470 | 288 | 117 | **102** | 96 | 2 |
| House P0002 | 1323 | 648 | 177 | **164** | 145 | 3 |
| **合计** | 3899 | — | — | **1827** | **1776** | **23** |

"切块"的必要性:转换器的共视分数矩阵是 O(n²) 次全图几何一致性检验
(本机实测 **10.7 ms/对 @768×576**),且轨迹上相隔很远的帧本来就没共视。
所以按轨迹序切成 ≤120 帧的连续块,块内帧号断层超过阈值就断开
(Office max_gap=15/chunk_min=20;House 因亮帧稀疏放宽到 max_gap=30/chunk_min=15)。
块内共视不足的 ref 会在 pair.txt 里 src 数不够,`blend.py::build_list` 自动丢弃,
所以放宽 gap 是安全的 —— 有硬闸在后面兜。

⚠️ 对照口径修正:Office P0000 的 0.617 不要再表述为"相对手机域 N×"。真实手机域
9 个独立会话的 f100 中位分布是 0.149~0.538(中位 0.482,数据在
`step0/phone_multi/res_*.json`),b28 那 132 帧(0.209)是分布谷底不是代表值。

### 步骤 3:转换

转换器加了三个**加法式**入口(不给就与旧行为逐字节一致):
`--frame_ids_json`(按帧号列表选帧)、`--out_w/--out_h`(尺寸对齐)。
另外 pair.txt 写出后新增一行打印「每 ref 的 src 数 min/median/max + src>=8 的 ref 数」,
因为 `blend.py::build_list` 会静默丢弃 src 数 < trainviews-1 的 ref。

尺寸对齐做法:640×640 --中心裁--> 640×480(4:3,与 768×576 同宽高比,off 0,80)
--各向同性 ×1.2--> 768×576;内参同步(cy -= 80,再整体 ×1.2),深度用 INTER_NEAREST。
**768×576 已核实是 BlendedMVS/MVG 的真实图像尺寸**(出处:
`experiments/casdiffmvs_blendmvg_scratch_2026-08-16/H200_RUN_FINDINGS.md`
「图像 768×576,共 35638 张」,该数字是上次租机实测)。

驱动脚本 `convert_all.sh`,产物 `finetune_pack/tg_mvs/{scan}/{blended_images,cams,rendered_depth_maps}`。

### 步骤 5:验收脚本 —— 🔴 跑通了,但暴露了一个更重要的问题

一键脚本 `eval_ckpt.sh --ckpt X --tag Y` 已在 mvgZeroDTU.ckpt 上跑通全链
(推理→融合→官方评测→带 viz 的官方评测→分区域指标→markdown 表)。
`region_metrics.py` 的 ALL-vs-official 自证 **PASSED,worst=3.769e-07**
—— 说明分区域聚合这一层是忠实的。

**但同一个 ckpt 复跑并没有复现 08-24 的数字。** 同 ckpt、同输入、同固定噪声
(seed=20260818+帧号)、同机器、同一天,三次运行的融合点云规模:

| 运行 | dense ply 字节 |
|---|---|
| 08-24 14:17 原始(tag `new`) | 46,295,596 |
| 本次 selfcheck | 45,865,591 |
| 本次 selfcheck2(与 selfcheck 完全同命令) | 48,280,981 |

官方指标 ALL 口径:acc@1cm 0.741918(原始) vs 0.721109(selfcheck),差 **2.08pp**;
分区域最大差 **6.16pp**(天花板 comp@1cm)。

⇒ **这条链在 MPS 上不是确定性的,复跑噪声地板(≥2pp ALL / ≥6pp 分区域)比
这场战役一直在报的效应量(墙 +1.17pp@2cm 之类)还大。**
在把 TG 微调结果拿去和 08-24 的数字比之前,必须先量这个噪声地板:
同一 ckpt 跑 N≥3 次,把区间画出来。已写进 RUNBOOK 第 6 节 + `noise_floor.sh`。

三次完整数字(同 ckpt / 同输入 / 同固定噪声 seed=20260818+帧号):

| 容差 | comp 原始/复跑1/复跑2 | acc 原始/复跑1/复跑2 | F1 原始/复跑1/复跑2 |
|---|---|---|---|
| 1cm | 0.302709 / 0.301531 / 0.296299 | 0.741918 / 0.721109 / 0.731972 | 0.429982 / 0.425246 / 0.421839 |
| 2cm | 0.382947 / 0.386406 / 0.373459 | 0.880684 / 0.861905 / 0.873611 | 0.533788 / 0.533593 / 0.523239 |
| 5cm | 0.463873 / 0.470881 / 0.454297 | 0.975125 / 0.967122 / 0.970072 | 0.628679 / 0.633378 / 0.618802 |
| 10cm | 0.538528 / 0.547199 / 0.531702 | 0.997602 / 0.994377 / 0.994963 | 0.699468 / 0.705930 / 0.693045 |

`region_metrics.py` 的 ALL-vs-official 自证在复跑上 **PASSED(worst 3.769e-07)**
—— 也就是说不确定性来自推理/融合,不是来自分区域聚合那一层。

### 步骤 3 的抽验 + 一个必须交给用户拍板的发现

抽验脚本 `verify_with_official_loader.py` —— **直接 import 官方 `datasets/blend.py`
的 MVSDataset,按训练时一模一样的方式(mode='train'/nviews=9/ndepths=384)真实
`__getitem__`**,不自己写读取逻辑。检查:分辨率唯一、imgs 值域 [0,1]、
四个 stage 的 depth 尺寸与内参缩放比恰好 8/4/2/1、depth_values 单调且首尾等于
1/depth_max 与 1/depth_min、stage4 mask 有效占比。

**全部 23 个 scan 抽 20 样本:全部通过。**
官方 `build_list()` 报 `dataset train metas: 1774`(1776 帧里只有 2 个 ref 因
src 不足 8 被官方逻辑丢弃 —— 安全阀在起作用,丢弃率 0.11%)。
分辨率集合 `{(576, 768)}` 唯一;stage4 mask 有效占比中位 **97.3%**、最低 **93.2%**。

🟡 **但抽验暴露了一个会静默伤训练的问题,已做成可开关的工具交给用户拍板:**
转换器按 1/99 百分位取 `[depth_min, depth_max]`,而 TG 的 Office/House 是
**室内但有窗**,窗外天空在 AirSim 深度里几百米,99 百分位被污染。
**全部 1776 个 cam.txt 实测**:depth_max 中位 17.98 m,但 p75=155.16 m、p90=233.06 m,
**>100 m 的帧 663/1776 = 37.3%**。`blend.py` 把这个范围切成 384 个视差等距假设,
depth_max 从 15 m 变成 250 m 就意味着假设大半浪费在"很远"那一端。
工具 `retighten_depth_range.py`(只改 cam.txt 最后一行,`.orig` 备份,可 `--revert`):
`--hi 95` 之后 >100 m 的帧 **663→112**,depth_max p75 **155.16→14.61 m**。
**没有默认应用** —— 这是会改结果的选择,写进 RUNBOOK 第 6.5 节让用户拍板。

### 步骤 4:训练配方

三个脚本:
- `make_mixed_list.py`:按目标比例把 TG scan 混进 BlendedMVG 清单。零代码改动
  (软链 + 清单里重复行);`R = ratio·N_mvg/((1−ratio)·N_tg)`;
  若 TG 单份已超目标则改为按 scan 名排序贪心抽子集(确定性)。两条分支都跑过烟测。
- `finetune_tgmix.sh calib|run`:照抄官方 `train_casdiffmvs.sh` 的 BlendedMVS 段,
  有意差异只有三条(loadckpt / trainlist / epochs=4)。`calib` = 200 步定标模式。
- `download_blendedmvg.sh`:GitHub Releases API 现取资产清单 + 逐字节核对 + 断点续传。
  已核对 v1.0.0(BlendedMVS 27.5 GiB)/ v1.0.1(BlendedMVS+ 81.7 GiB)/
  v1.0.2(BlendedMVS++ 80.01 GiB,42 个分卷各 2,044,723,200 B)。

### 步骤 6:交付

`RENTED_MACHINE_RUNBOOK.md` + `vendored/`(原样带上的上游脚本:prep_h100.sh /
blend_cached.py / predecode_blend.py / make_blendmvg_list.py / run_arm.py /
fuse_arm.py / lowtex.py / colmap_input_patched.py)。

## 🔴 还没闭合的缺口

1. **b28 TSDF 网格对比页没有生成脚本。** `verdict_page/tsdf/bin/{tsdf,tsdf_clean}.{pos,idx,col}`
   在磁盘上,但 `find -name "*tsdf*"` 在 `_host_experiments/` 与
   `research-benchmarks/experiments/` 下只找到这一个目录,**没有找到造它的代码**。
   判决腿 2(用户肉眼)因此缺一条可照抄的命令。
2. `multi-view-evaluation` 的 cmake/make 编译命令、ETH3D office 数据的下载 URL,
   历史上都没有被记录(二进制与数据都在 Mac 磁盘上)。租用机要跑验收链得先解决。
3. `region_metric_20260824/cache/gt_labels_altwall.npy` **没有生成脚本**(五个 .py 全查过,
   只有读没有写)。它与 ckpt 无关,必须整份拷贝,不能重建。
