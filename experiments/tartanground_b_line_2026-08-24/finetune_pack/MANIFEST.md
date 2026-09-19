# 弹药包清单 —— `/Users/kaidongwang/Developer/tartanground_b_line/finetune_pack/`

**核对于 2026-08-25**:23 个 scan / 1776 帧 / 3.1 GB;官方 dataloader 建表
**1774 个训练样本**(trainviews=9);分辨率唯一 576×768;
stage4 mask 有效占比中位 97.3%、最低 93.2%。
(数量类字段可用「六、MANIFEST 自检」的命令随时现场重核。)

**实验设计(用户拍板)**:主实验**只有一臂 B**(TG 20% 混合微调,1 份卡时),
对照是现有 `mvgZeroDTU.ckpt` **零成本**,臂 A(不掺 TG 的同量续训)是**条件臂**
—— 只在 B 有真增益时才补跑;臂 C(Prism 式蒸馏)**本次不做**,配方存 RUNBOOK 附录 D。

## 一、必读文档

| 文件 | 是什么 |
|---|---|
| `RENTED_MACHINE_RUNBOOK.md` | **租用机执行手册**。从上传弹药包到出判决，逐步命令 + 每步预期产物。 |
| `PROGRESS.md` | 制备过程的增量记录：每一步的实测数字、做过的判断、踩到的坑。 |
| `MANIFEST.md` | 本文件。 |

## 二、数据产物（要传到租用机的部分）

| 路径 | 内容 |
|---|---|
| `tg_mvs/<scan>/blended_images/{:08d}.jpg` | 768×576 RGB |
| `tg_mvs/<scan>/cams/{:08d}_cam.txt` | extrinsic 4×4 + intrinsic 3×3 + `depth_min interval num depth_max` |
| `tg_mvs/<scan>/cams/pair.txt` | 官方格式共视表（官方角度-高斯打分公式 + 官方 filter.py 几何一致性判据） |
| `tg_mvs/<scan>/rendered_depth_maps/{:08d}.pfm` | 768×576 float32 米制 z-depth |
| `tg_mvs/<scan>/conversion_meta.json` | 该 scan 的转换元数据（帧号、分辨率、内参、resize 配置、每 ref 的 src 数下限） |
| `tg_mvs/lists_all_scans.txt` | 全部 scan 名，一行一个 —— 给 `make_mixed_list.py --tg_list` |
| `sel/*.json` | 每个 scan 选中的轨迹帧号列表 |
| `sel/*_selection.json` | 选帧统计（各阶段留多少帧） |
| `tex_TG_*.json` | 全轨迹逐帧纹理分数（`lowtex.py --n -1`，THR=100） |
| `baseline_mvgZeroDTU.json` | 08-24 那次 mvgZeroDTU 在 26 帧 office 上的官方 + 分区域数字（逐字抄，做对比用） |

## 三、脚本（本包自写）

| 脚本 | 做什么 |
|---|---|
| `download_tg.py` | 从 HF `theairlabcmu/TartanGround` 补下 depth/pose/image，逐字节核对 + 断点续传 |
| `select_frames.py` | 按 f100/亮度筛白墙帧，按轨迹序切成可转换的 scan 分块 |
| `convert_all.sh` | 驱动 `tartanground2mvsnet.py` 批量转换（可传 `OUT_ROOT W H PARALLEL`） |
| `verify_with_official_loader.py` | **用官方 `datasets/blend.py` 真实 `__getitem__`** 抽验产物 |
| `retighten_depth_range.py` | 🟡 决定项：重算 cam.txt 深度范围（`.orig` 备份，`--revert` 可还原） |
| `download_blendedmvg.sh` | 租用机上下 BlendedMVG（GitHub Releases API 取清单 + 逐字节核对） |
| `make_mixed_list.py` | 按比例把 TG 混进 BlendedMVG 清单（软链 + 重复行，**零代码改动**） |
| `finetune_tgmix.sh` | `calib`（200 步定标）/ `run`（正式续训），照抄官方 train.py 调用方式 |
| `eval_ckpt.sh` | **一条命令**：ckpt → 推理 → 融合 → 官方评测 → 分区域指标 → markdown 表 |
| `noise_floor.sh` | 同 ckpt 跑 N 次，量复跑噪声地板 |
| `region_metrics_tags.py` | `region_metrics.py` 的可参数化外壳（只换模块级 `TAGS`，算法零复制） |
| `region_tables.py` | 任意 tag 数的表格渲染（官方 `make_tables.py` 把三臂列名写死了） |

## 四、`vendored/` —— 原样带上的上游脚本（不是重写）

| 文件 | 来源 |
|---|---|
| `prep_h100.sh` / `blend_cached.py` / `predecode_blend.py` / `make_blendmvg_list.py` | `experiments/casdiffmvs_blendmvg_scratch_2026-08-16/tools/` |
| `run_arm.py` / `fuse_arm.py` | `experiments/mvs_pose_ablation_2026-08-18/tools/` |
| `lowtex.py` | `tartanground_b_line/step0/` |
| `colmap_input_patched.py` | `ethd3d_a_line/run_20260824/tools_patched/`（一行调试 print 补丁） |

`tartanground2mvsnet.py`（转换器本体）也拷了一份在包根目录，本次给它加了三个
**加法式**入口：`--frame_ids_json` / `--out_w` / `--out_h`（不给就与旧行为逐字节一致）。
上游原件在 `/Users/kaidongwang/Developer/tartanground_b_line/tartanground2mvsnet.py`（同一份）。

## 五、**不在包里、必须另外准备**的东西

| 东西 | 为什么不在包里 | 怎么办 |
|---|---|---|
| BlendedMVG 数据 | 189 GiB 压缩 | `download_blendedmvg.sh` 在租用机上下 |
| `casdiffmvs_mvgZeroDTU.ckpt` | 在 `_host_experiments/` 下 | 单独 scp（11.7 MB） |
| ETH3D office 数据 + `ETH3DMultiViewEvaluation` 二进制 | 442 MB + 需编译 | scp 或重下重编（**下载 URL 与编译命令历史上没被记录**） |
| `region_metric_20260824/cache/*.npy` | 463 MB+，且 `gt_labels_altwall.npy` **没有生成脚本** | 必须整份 scp，不能重建 |
| b28 TSDF 对比页的生成脚本 | **找不到**（见 RUNBOOK 8.2） | 未闭合缺口 |

## 六、MANIFEST 自检

```bash
cd /Users/kaidongwang/Developer/tartanground_b_line/finetune_pack
echo "scan 数        : $(ls tg_mvs/*/conversion_meta.json | wc -l)"
echo "清单行数       : $(wc -l < tg_mvs/lists_all_scans.txt)"
echo "图像总数       : $(ls tg_mvs/*/blended_images/*.jpg | wc -l)"
echo "深度总数       : $(ls tg_mvs/*/rendered_depth_maps/*.pfm | wc -l)"
echo "cam.txt 总数   : $(ls tg_mvs/*/cams/*_cam.txt | wc -l)"
echo "tg_mvs 体积    : $(du -sh tg_mvs | cut -f1)"
python3.11 verify_with_official_loader.py --root tg_mvs --list tg_mvs/lists_all_scans.txt --nviews 9 --n 20
```
