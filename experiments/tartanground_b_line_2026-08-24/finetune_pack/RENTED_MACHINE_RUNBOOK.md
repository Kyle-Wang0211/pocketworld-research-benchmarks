# 租用机执行手册 —— TG 白墙子集 × mvgZeroDTU 续训

> 目标:拿到一台 5090(或更大显存的卡)之后,照着这份文档从上到下敲,
> **30 分钟内进入训练**。所有会花很长时间的事(下数据、选帧、转格式、写脚本、
> 把验收链跑通)已经在 Mac 上做完了,弹药包在
> `/Users/kaidongwang/Developer/tartanground_b_line/finetune_pack/`。

编写日期 2026-08-24。所有路径都是绝对路径。解释器:Mac 上是 `python3.11`,
租用机上按当地环境用 `python3`/`python`。

---

## 0. 先读这一节:这次要做什么、判决怎么做出来

### 0.1 实验设计(用户已拍板,不要自行扩张)

| 臂 | 内容 | 卡时 | 状态 |
|---|---|---|---|
| **B(主实验,唯一要训的)** | 从 `casdiffmvs_mvgZeroDTU.ckpt` 微调,数据 = **BlendedMVG + TG_Office/House 白墙帧**(Office `f100>0.4`;House 先 `mean_gray≥90` 再 `f100>0.4`),TG 占比 **20%**,epochs=4 | 1 份 | **要跑** |
| **对照** | 现有 `casdiffmvs_mvgZeroDTU.ckpt` **原样**,不训 | **0** | 已有权重,只需跑验收链 |
| **A(条件臂)** | 同数据量同轮数、但**不掺 TG** 的续训对照,用来把"是 TG 的功劳"和"只是多训了几轮"分开 | 1 份 | **只在 B 相对对照有增益时才补跑**;B 无增益就不跑 —— 见第 7.5 节 |
| **C(Prism 式蒸馏)** | 本次**不做** | 0 | 配方留在附录 D |

⇒ **主线的卡时 = 1 份微调 + 若干次验收链推理**,不是三臂扫参。
只有在 B 出现真增益(大于第 6 节的噪声地板)时,才追加第二份训练(A)。

### 0.2 判决是怎么做出来的

**代理统计不判决。** 纹理占比 f100、阈值、"比手机域高几倍"这类数字,
只用来**筛帧**(选出白墙帧),不用来判"这次微调成没成"。

**唯一的判决闭环,两条腿缺一不可:**

| # | 判据 | 怎么出 |
|---|---|---|
| 1 | **ETH3D office 全链验收** —— 官方 accuracy/completeness/F1 四档 + 分区域(墙/天花板/地板/杂物)completeness@1/2/5cm | `bash eval_ckpt.sh --ckpt <新权重> --tag <名字>`(第 7 节) |
| 2 | **b28 场景的 TSDF 网格对比页,用户肉眼判定** | 第 8 节(⚠️ 有一个已知缺口,见那一节) |

判据 1 的数字必须先减掉**复跑噪声地板**才有意义 —— 见第 6 节,这是本次准备
过程中挖出来的新问题,以前没量过。

**BlendedMVG 的同口径纹理统计(第 5 节)只是参考信息,不是开训/停止的门。**

---

## 1. 机器与磁盘要求

| 项 | 要求 | 出处 |
|---|---|---|
| 显存 | ≥24 GB(batch 4 实测占 22 GB)。5090 是 32 GB,够。 | `experiments/casdiffmvs_blendmvg_scratch_2026-08-16/H200_RUN_FINDINGS.md` |
| 内存 | 越大越好。预解码缓存要整份驻留页缓存才有意义(BlendedMVS 一档缓存 48.7 GiB) | 同上 |
| 磁盘 | BlendedMVG 全量:压缩 189 GiB + 解压 261 GiB + 缓存 ⇒ **保守 1 TB**;只用 BlendedMVS 一档则 150 GB | 同上 |
| vCPU | 有预解码缓存后不是硬门槛,但预解码那一次会慢 | 同上 |

---

## 2. 把弹药包传上去(≈4 GB)

Mac 端:

```bash
cd /Users/kaidongwang/Developer/tartanground_b_line
tar -czf /tmp/tg_finetune_pack.tar.gz \
    finetune_pack/tg_mvs \
    finetune_pack/vendored \
    finetune_pack/sel \
    finetune_pack/*.sh finetune_pack/*.py finetune_pack/*.json finetune_pack/*.md
# ⚠️ 不要打包 finetune_pack/raw 与 finetune_pack/unz(TG 原始 zip 与解压件,
#    合计 ~7 GB,租用机上用不到 —— 转换已经在 Mac 上做完了)
scp /tmp/tg_finetune_pack.tar.gz root@<租用机>:/data/
# 续训起点权重(11.7 MB)
scp /Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/casdiffmvs_mvgZeroDTU.ckpt \
    root@<租用机>:/data/
```

租用机端:

```bash
cd /data && tar -xzf tg_finetune_pack.tar.gz
ls /data/finetune_pack/tg_mvs/*/conversion_meta.json | wc -l   # 预期 23
ls /data/finetune_pack/tg_mvs/*/blended_images/*.jpg | wc -l   # 预期 1776
ls /data/finetune_pack/tg_mvs/*/rendered_depth_maps/*.pfm | wc -l  # 预期 1776
```

**Mac 上已核对过的数**:23 个 scan / 1776 帧 / 3.1 GB;
用官方 dataloader 建表得 **1774 个训练样本**(2 个 ref 因 src<8 被官方逻辑丢弃),
分辨率唯一 576×768,stage4 mask 有效占比中位 97.3%。

**预期产物**:`/data/finetune_pack/tg_mvs/<scan>/{blended_images,cams,rendered_depth_maps}`,
每个 scan 目录里 `cams/pair.txt`、`cams/{:08d}_cam.txt`、`blended_images/{:08d}.jpg`(768×576)、
`rendered_depth_maps/{:08d}.pfm`(768×576 float32,米制)。

---

## 3. 环境 + 官方仓库 + dataloader 补丁(≈5 分钟)

直接复用上次租机写好的脚本(不要重写):

```bash
cd /data/finetune_pack/vendored          # prep_h100.sh 会从自己所在目录拷 blend_cached.py
MVG_ROOT=/data/BlendedMVG DIFFMVS_DIR=/root/diffmvs bash prep_h100.sh
```

`vendored/` 里已经把要用的上游脚本原样带上了(不是重写):
`prep_h100.sh` / `blend_cached.py` / `predecode_blend.py` / `make_blendmvg_list.py`
(来自 `experiments/casdiffmvs_blendmvg_scratch_2026-08-16/tools/`)、
`run_arm.py` / `fuse_arm.py`(来自 `experiments/mvs_pose_ablation_2026-08-18/tools/`)、
`lowtex.py`(来自 `tartanground_b_line/step0/`)、
`colmap_input_patched.py`(来自 `ethd3d_a_line/run_20260824/tools_patched/`)。

`prep_h100.sh` 会:体检机器 → `git clone https://github.com/cvg/diffmvs.git` →
给 `train.py` 打 `NUM_WORKERS` 补丁(**只影响吞吐不影响数值**,原文件存为 `train.py.orig`)
→ 装 `datasets/blend_cached.py`。

🔴 **必须核对一件事**:官方仓库的 `datasets/blend.py` 全程不 resize 图像,
`DataLoader` 默认 collate 要求同 batch 内张量同形状。我们的 TG scan 是按
**768×576** 转的。上机后先量一眼 BlendedMVG 的真实尺寸:

```bash
python3 -c "
from PIL import Image; import glob
p=glob.glob('/data/BlendedMVG/*/blended_images/00000000.jpg')[0]
print(p, Image.open(p).size)"
```

期望打印 `(768, 576)`。**如果不是**,TG 侧要在 Mac 上用
`bash convert_all.sh <out_root> <W> <H>` 重转一遍再传上来(转换约 40 分钟)。

---

## 4. 下 BlendedMVG(长跑,放后台)

```bash
bash /data/finetune_pack/download_blendedmvg.sh /data/blendedmvg_zips all
# 只要 BlendedMVS 一档:  ... /data/blendedmvg_zips mvs
```

脚本从 GitHub Releases API 现取资产清单与逐个字节数(不写死),
`curl -C - --speed-time 60 --speed-limit 10000` 治 CDN 静默失速,
每个文件下完与 API 报的 size 逐字节核对,不一致自动重下。

**预期产物**:`/data/blendedmvg_zips/BlendedMVS{,1,2}.z01..` + `.zip`。
合并解压命令脚本跑完会打印出来(`zip -s 0 X.zip --out combined.zip && unzip`)。

然后建清单 + **全量体检**(不是抽查 —— `blend.py` 在 `__getitem__` 才拼路径,
缺文件要等训练跑到那个样本才炸):

```bash
python3 /data/finetune_pack/vendored/make_blendmvg_list.py /data/BlendedMVG /data/lists
```

**预期产物**:`/data/lists/{train.txt,val.txt,report.txt}`。
`val.txt` 是官方那 7 个场景,保持与历史数字可比。

---

## 5. (参考信息,不是门)BlendedMVG 的同口径纹理统计

这一步回答的是"我们缺的白墙监督,BlendedMVG 里到底有多少",
**结果只写进报告,不决定开不开训**。

```bash
python3 /data/finetune_pack/vendored/lowtex.py \
   --dir /data/BlendedMVG --name BlendedMVG --n 2000 --thr 100 \
   --out /data/tex_BlendedMVG.json
python3 -c "
import json,numpy as np
d=json.load(open('/data/tex_BlendedMVG.json')); f=np.array([r['f100'] for r in d['rows']])
print('n=%d  f100 中位=%.3f  均值=%.3f  >0.4 占比=%.1f%%'%(len(f),np.median(f),f.mean(),(f>0.4).mean()*100))"
```

口径与 TG/手机侧完全一致(`step0/lowtex.py`:灰度 → 短边缩到 640 → Sobel k=3 →
`g²` → 5×5 box → `f100 = (E<100).mean()`)。⚠️ `lowtex.py` 递归遍历目录,
BlendedMVG 里 `*_masked.jpg` 变体也会被数进去,而 `blend.py` 从不读它们 ——
要干净口径就先 `find /data/BlendedMVG -path '*blended_images/*' -name '[0-9]*.jpg'`
建一个只含真训练图的目录再统计。

已知对照数(同口径,本机实测):

| 组 | f100 中位 |
|---|---|
| TG_Office P0000 | **0.617** |
| TG_Office P0001 | 0.488 |
| TG_House P0000 | 0.468(但平均灰度只有 56.9 —— 高分一半来自"太黑"不是"平") |
| 真实手机域(9 个独立会话) | 0.149~0.538,**中位 0.482** |
| 其中 b28 那 132 帧 | 0.209(是分布**谷底**,不是代表值) |

---

## 6. 🔴 先量复跑噪声地板,再谈判决(本次新增,以前没做过)

**这是本次准备过程中挖出来的问题。** 在 Mac 上用**同一个** `mvgZeroDTU.ckpt`、
同输入、同固定噪声(`--noise_seed 20260818`,噪声只依赖帧号)、同机器、同一天,
跑三次整条验收链:

| 运行 | dense ply 字节 | comp@1cm | acc@1cm | F1@1cm |
|---|---|---|---|---|
| 08-24 14:17 原始(tag `new`) | 46,295,596 | 0.302709 | 0.741918 | 0.429982 |
| 复跑 1 | 45,865,591 | 0.301531 | 0.721109 | 0.425246 |
| 复跑 2 | 48,280,981 | 0.296299 | 0.731972 | 0.421839 |
| **极差** | **5.3%** | **0.64 pp** | **2.08 pp** | **0.81 pp** |

分区域指标的极差更大:天花板 completeness@1cm 差 **6.16 pp**,墙 accuracy@2cm 差 **2.72 pp**。

⇒ **这条链不是确定性的**,而噪声地板比这场战役一直在报的效应量还大
(比如"新权重 vs 官方 blendmvg 墙 +1.17pp@2cm" 完全落在地板以内)。

**所以上机第一件评测事项是量地板,不是评新权重:**

```bash
bash /data/finetune_pack/noise_floor.sh --ckpt /data/casdiffmvs_mvgZeroDTU.ckpt --tag base --n 3
```

**预期产物**:`eval_runs/noisefloor_base/noise_floor.json` + 一张极差表。
⚠️ 上面那组数是 **MPS** 上量的,租用机是 CUDA,**必须在租用机上重量一遍**
(CUDA 上 cudnn benchmark/atomics 也会带来非确定性,量级未知)。

**判据写死**:微调后的指标提升,必须**大于地板极差**才算数;落在地板以内
一律记为"没有可测的差异",不许写成"小幅提升"。

---

## 6.5 🟡 决定项 #1:TG 的深度范围要不要收紧(2 分钟,建议做)

转换器按官方常见做法取深度 1/99 百分位当 `[depth_min, depth_max]`。
TartanGround 的 Office/House **室内但有窗**,窗外天空在 AirSim 深度里是几百米,
99 百分位被污染。全部 cam.txt 实测:

| | 现状(p99) |
|---|---|
| depth_max 中位 | 17.98 m |
| depth_max p75 / p90 / p99 | 155.16 / 233.06 / 308.25 m |
| **depth_max > 100 m 的帧** | **663 / 1776 = 37.3%** |

`blend.py` 用这个范围生成 384 个**视差**等距采样
(`linspace(1/depth_max, 1/depth_min, 384)`)。depth_max 从 15 m 变成 250 m,
384 个深度假设大半压在"很远"那一端,真正的室内 1–15 m 段被挤薄 —— 静默伤训练。

```bash
python3 /data/finetune_pack/retighten_depth_range.py --root /data/finetune_pack/tg_mvs --hi 95 --dry_run
python3 /data/finetune_pack/retighten_depth_range.py --root /data/finetune_pack/tg_mvs --hi 95
# 反悔: --revert
```

改 p95 之后:>100 m 的帧 **663 → 112**,depth_max p75 **155.16 → 14.61 m**。
**只改 cam.txt 最后一行,图像/深度/pair.txt 一律不动,原文件留 `.orig` 可随时还原。**
⚠️ 这是一个"改了会影响结果"的选择,不是纯工程动作;要不要做请**明确记录**在实验记录里,
两个臂之间不要一个改一个不改。

---

## 7. 建混合清单 → 定标 → 开训

### 7.1 建混合清单(30 秒)

```bash
python3 /data/finetune_pack/make_mixed_list.py \
   --mvg_root /data/BlendedMVG --mvg_list /data/lists/train.txt --mvg_val /data/lists/val.txt \
   --tg_root  /data/finetune_pack/tg_mvs \
   --tg_list  /data/finetune_pack/tg_mvs/lists_all_scans.txt \
   --ratio 0.2 --trainviews 9 \
   --out_root /data/mixed --out_lists /data/mixed_lists
```

原理(读过 `datasets/blend.py::build_list` 之后定的,**网络代码一行不改**):
`MVSDataset` 只吃 `(datapath, listfile)`,清单里同一个 scan 名写两遍就产生两份样本。
所以 ①`/data/mixed` 是一堆软链(MVG 的每个 scan + TG 的每个 scan);
②清单 = MVG 各一行 + TG 各重复 R 行,R 由目标比例反解:
`R = ratio·N_mvg / ((1−ratio)·N_tg)`。
样本数按 `build_list` 的口径算(src 数 ≥ trainviews−1 的 ref 才算,不够的会被静默丢弃)。

**主线只用 20% 一档**(见第 0 节:主实验只有一臂 B)。
10%/40% 两档的清单可以顺手一起建出来备用,建清单是秒级的、**不额外花卡时**;
但**不要**顺手把它们也训了 —— 那就变成三臂扫参,不是本次的设计。

```bash
for r in 0.1 0.2 0.4; do
  python3 /data/finetune_pack/make_mixed_list.py \
     --mvg_root /data/BlendedMVG --mvg_list /data/lists/train.txt --mvg_val /data/lists/val.txt \
     --tg_root /data/finetune_pack/tg_mvs --tg_list /data/finetune_pack/tg_mvs/lists_all_scans.txt \
     --ratio $r --out_root /data/mixed --out_lists /data/mixed_lists
done
```

**预期产物**:`/data/mixed_lists/train_tg10.txt`、`train_tg20.txt`、`train_tg40.txt`、
`val.txt`(纯 MVG)、`mix_tgXX.json`(记录实际达成比例、R、样本数)。
**主线用 `train_tg20.txt`。**

### 7.2 预解码缓存(可选但强烈建议,一次性 <60 秒~几分钟)

```bash
python3 /data/finetune_pack/vendored/predecode_blend.py /data/mixed /data/mixed_lists/train_tg20.txt \
        /data/cache --nviews 9 --depth --repo /root/diffmvs
```
🔴 跑完看它报的合计体积,必须明显小于 `free -g` 的 available,否则反复回盘。
`blend_cached` 只把 `read_img/read_depth` 换成读 mmap,喂给模型的张量逐位相同。

### 7.3 定标(200 步,量单步耗时与显存)

```bash
cd /data/finetune_pack
DIFFMVS_DIR=/root/diffmvs \
MIX_ROOT=/data/mixed TRAINLIST=/data/mixed_lists/train_tg20.txt VALLIST=/data/mixed_lists/val.txt \
LOADCKPT=/data/casdiffmvs_mvgZeroDTU.ckpt BLEND_CACHE=/data/cache \
bash finetune_tgmix.sh calib
```

从日志读两个数(别再估):`dataset train metas:` = 每轮样本数;`time=` = 每 iter 秒数。
小时数 =(样本数 ÷ batch)× epochs × 每iter秒 ÷ 3600。
后台会在 120 秒时打一次 `nvidia-smi`,给出单进程显存。

### 7.4 正式续训 —— **臂 B(本次唯一要训的)**

```bash
DIFFMVS_DIR=/root/diffmvs \
MIX_ROOT=/data/mixed TRAINLIST=/data/mixed_lists/train_tg20.txt VALLIST=/data/mixed_lists/val.txt \
LOADCKPT=/data/casdiffmvs_mvgZeroDTU.ckpt BLEND_CACHE=/data/cache EPOCHS=4 \
bash finetune_tgmix.sh run
```

**预期产物**:`runs_tgmix/train_tg20/model_00000*.ckpt` + `p1.log` / `p2.log`。

与官方 `scripts/train/train_casdiffmvs.sh` 的 BlendedMVS 段相比,**有意差异只有三条**:
`--loadckpt` 指向 mvgZeroDTU、`--trainlist` 指向混合清单、`--epochs` 默认 4(官方 16,
因为这是微调不是从头训)。其余逐字保持官方值:
`--trainviews/--testviews 9`、`--numdepth 384`、`--numdepth_initial 48`、
`--stage_iters 1 3 3`、`--cost_dim_stage 4 4 4`、`--CostNum 0 4 4`、
`--min_radius 0.125`、`--max_radius 8`、`--hidden_dim 0 32 20`、
`--context_dim 32 32 16`、`--unet_dim 0 16 8`、`--lr 0.001`、`--lr_sche onecycle`、
`--conf_weight 0.05`(⚠️ argparse 默认是 1.0,不显式传会差 20 倍)。
`--scale` 走官方 blend 段的两档课程:前半 `0 0.25 0.05`,后半 `0 0.125 0.025`。

(如果以后要扫比例:把 `TRAINLIST` 换成 `train_tg10/40.txt`,别的都不动。
**本次不扫** —— 见第 0.1 节。)

### 7.5 条件臂 A —— **只在 B 有增益时才跑**

**触发条件(三条同时满足才跑 A):**

1. 臂 B 的 ETH3D **墙区 completeness**(@1cm / @2cm / @5cm 中至少两档)高于
   `mvgZeroDTU` 对照;
2. 该差值 **大于第 6 节在本机量出来的噪声地板**;
3. 用户看过 b28 TSDF 对比页,没有推翻。

**任一条不满足 ⇒ 不跑 A,直接结题**(结论就是"TG 白墙子集在这个配方下没带来
可测的增益"),别为了"做全"而烧第二份卡时。

**A 是什么:** 同样从 `mvgZeroDTU.ckpt` 出发、**同样的样本数、同样的 epochs**,
但**一点 TG 都不掺**。它回答的唯一问题是:B 的增益到底来自"掺了 TG 白墙",
还是仅仅来自"在 BlendedMVG 上又多训了 4 轮"。

```bash
# 造一份"样本数与 tg20 相同、但全是 MVG"的清单:
python3 - <<'PY'
import json, random
mix = json.load(open('/data/mixed_lists/mix_tg20.json'))
mvg = [l.strip() for l in open('/data/lists/train.txt') if l.strip()]
# tg20 里 TG 贡献的样本数,用重复 MVG scan 顶上,保证每轮样本数与 B 一致
import subprocess
need = mix['total_metas'] - mix['mvg_metas']
random.seed(0)
extra, acc = [], 0
# 每个 MVG scan 的样本数从 mix json 里没有存,这里用 pair.txt 现数(与 build_list 同口径)
def metas(scan):
    p = f"/data/BlendedMVG/{scan}/cams/pair.txt"
    with open(p) as f:
        n = int(f.readline()); ok = 0
        for _ in range(n):
            f.readline()
            ok += len(f.readline().split()[1::2]) >= 8
    return ok
pool = mvg[:]
while acc < need:
    s = random.choice(pool); extra.append(s); acc += metas(s)
with open('/data/mixed_lists/train_armA.txt', 'w') as f:
    for s in mvg + extra: f.write(s + '\n')
print('armA 清单:', len(mvg)+len(extra), '行,追加样本', acc, '目标', need)
PY

DIFFMVS_DIR=/root/diffmvs \
MIX_ROOT=/data/mixed TRAINLIST=/data/mixed_lists/train_armA.txt VALLIST=/data/mixed_lists/val.txt \
LOADCKPT=/data/casdiffmvs_mvgZeroDTU.ckpt BLEND_CACHE=/data/cache EPOCHS=4 TAG=armA \
bash finetune_tgmix.sh run
```

然后 `eval_ckpt.sh --ckpt <A 的权重> --tag armA --baseline new,tg20`,三列同表看。

---

## 8. 验收(判决腿 1 + 腿 2)

### 8.1 腿 1 —— ETH3D office 全链(一条命令)

```bash
bash /data/finetune_pack/eval_ckpt.sh --ckpt <新权重.ckpt> --tag tg20 --baseline new
```

一条命令串起五步:推理(`run_arm.py --num_view 10 --max_w 768 --max_h 576`,
固定噪声 seed=20260818+帧号)→ 融合(`fuse_arm.py` → 官方 `filter.py::filter_depth`,
参数 `3, 1.0, 0.01, [0.3,0.5,0.5], "casdiffmvs", "general"`)→ 官方
`ETH3DMultiViewEvaluation --tolerances 0.01,0.02,0.05,0.1` → 同一个二进制再跑一次
三档 + 逐点 viz 点云 → `region_metrics.py` 分区域聚合(**原样复用,只把模块级
`TAGS` 换掉**,见 `region_metrics_tags.py`)→ markdown 表。

**预期产物**:
- `eval_runs/<tag>/dense_<tag>.ply`
- `eval_runs/<tag>/logs/eval_<tag>.log`(官方四档 Completenesses/Accuracies/F1-scores)
- `eval_runs/<tag>/region_results_<tag>.json`
- `eval_runs/<tag>/REGION_TABLES_<tag>.md`

**必须先看的一行**:`SELF-CHECK passed=True worst=…`。
它是把分区域聚合在"全部点"上重算一遍去对官方二进制打印的数(Mac 上实测
worst=3.769e-07)。**passed=False 就别看下面任何数字。**

**要看的判据是墙区**:`completeness | 墙 | 1cm/2cm/5cm`。
TG 补白墙监督如果起作用,应该体现在墙区 completeness 上,而不是整体 F1。
差值必须大于第 6 节量出来的地板。

⚠️ 这条链依赖的三样东西在 Mac 上,租用机上要么 scp 过去要么重建:
1. `multi-view-evaluation/build/ETH3DMultiViewEvaluation`(**构建命令没有被记录过**,
   标准 `cmake .. && make`);
2. ETH3D office 数据(`office_dslr_undistorted.7z` + `office_dslr_scan_eval.7z`,
   **下载 URL 也没有被记录过**,只留了 `dl.log` 两行 DONE);
3. `region_metric_20260824/cache/` 里的 GT 侧缓存
   `gt_merged_xyz.npy`(463 MB)/`gt_labels.npy`/`gt_labels_altwall.npy`/`gt_plane_id.npy`
   —— 这些**与 ckpt 无关**,直接拷过去就能复用。
   ⚠️ `gt_labels_altwall.npy` **没有生成它的脚本**(五个 .py 全 grep 过,只有读没有写),
   看起来是把 `segment_gt.py` 的 `WALL_MIN_*` 改松后重跑改名得到的。所以它必须拷,不能重建。

### 8.2 腿 2 —— b28 TSDF 网格对比页(用户肉眼)

现成页面在 `/Users/kaidongwang/Documents/progecttwo/_host_experiments/pose_ablation_20260818/verdict_page/tsdf/`
(`index.html` + `bin/{tsdf,tsdf_clean}.{pos,idx,col}`),b28 的 132 帧在同目录 `b28_named/`。
点云对比页(非网格)的导出器是同目录 `verdict_page/export_bins.py`
(`--dir <含 dense_*.ply 的目录> --out <bin目录> --arms a,b,c --ref a`)。

🔴 **已知缺口(不猜)**:`tsdf/bin/` 里那三个 `tsdf*.pos/.idx/.col` 是网格
(带 idx = 三角形索引),而我在
`_host_experiments/` 与 `research-benchmarks/experiments/` 下 `find -name "*tsdf*"`
**只找到这一个目录,没有找到生成它的脚本**。
所以"把新权重加进 TSDF 对比页"这一步目前**没有可照抄的命令**,
要么找出当初生成它的会话记录,要么用 Open3D 的 TSDF 集成重建一条(那就是新写代码,
需要先和用户确认口径)。**这是弹药包里唯一没有闭合的一环。**

---

## 9. 一页纸速查

```bash
# ① 上传弹药包 + 起点权重                        (第 2 节)
# ② prep_h100.sh 装环境/仓库/补丁                 (第 3 节)
# ③ 核对 BlendedMVG 图像尺寸 == 768x576           (第 3 节,不对就回 Mac 重转)
# ④ download_blendedmvg.sh + make_blendmvg_list.py(第 4 节,长跑)
# ⑤ lowtex.py 统计(参考信息,不是门)             (第 5 节)
# ⑥ noise_floor.sh --ckpt mvgZeroDTU --n 3        (第 6 节,🔴 先量地板)
# ⑥.5 retighten_depth_range.py --hi 95(决定项)  (第 6.5)
# ⑦ make_mixed_list.py × 三档比例                 (第 7.1)
# ⑧ predecode_blend.py                            (第 7.2)
# ⑨ finetune_tgmix.sh calib -> run                 (第 7.3/7.4)
# ⑩ eval_ckpt.sh --ckpt <新权重> --tag tg20        (第 8.1)
# ⑪ TSDF 对比页交用户肉眼                          (第 8.2,⚠️ 有缺口)
```

---

## 附录 A:如果 `mvs_office`(26 帧 MVSNet 格式输入)需要重建

```bash
WORK=<工作目录>
mkdir -p "$WORK/colmap_input/sparse"
ln -sf <ETH3D>/data/office/images "$WORK/colmap_input/images"
colmap model_converter \
  --input_path <ETH3D>/data/office/dslr_calibration_undistorted \
  --output_path "$WORK/colmap_input/sparse" --output_type BIN
python3 <打过补丁的>/colmap_input.py \
  --input_folder "$WORK/colmap_input" --output_folder "$WORK/mvs_office" --convert_format
```

补丁只有一行(`colmap_input.py:344`):官方把调试打印的相机 ID 硬编码成 `1`,
而 ETH3D office 的 `CAMERA_ID = 0`,会 `KeyError` 崩;改成
`next(iter(intrinsic.values()))`。**只是调试 print,不参与任何计算或写盘。**
Mac 上的副本在 `ethd3d_a_line/run_20260824/tools_patched/colmap_input.py`。

Mac 上还需要 `DYLD_LIBRARY_PATH=/opt/homebrew/Cellar/protobuf/35.1_2/lib` 前缀
才能启动 brew 装的 colmap(链的是 protobuf 35.1,而 `opt/protobuf` 软链指向 36.0)。
Linux 上不需要。

## 附录 B:已核实的基线数字(mvgZeroDTU,26 帧 office,08-24 14:17 那次)

存在 `finetune_pack/baseline_mvgZeroDTU.json`,逐字抄自
`ethd3d_a_line/run_20260824/logs/eval_new.log` 与
`region_metric_20260824/cache/region_results.json`。
⚠️ 用它做对比时务必带上第 6 节的噪声地板 —— 它只是**一次**采样,不是真值。

## 附录 C:脚本里所有硬编码路径的环境变量开关

弹药包里的脚本默认写的是 Mac 上的绝对路径,租用机上用下面这些环境变量覆盖,
**不需要改任何一行代码**:

| 变量 | 覆盖什么 | 默认值(Mac) |
|---|---|---|
| `PY` | Python 解释器 | `python3.11` |
| `DIFFMVS_REPO` | 官方 diffmvs 仓库 | `…/pocketworld_research_benchmarks/tools/python/diffmvs` |
| `ETH3D_LINE` | ETH3D 战线根目录(评测二进制/数据/eval_runs 都挂在下面) | `~/Developer/ethd3d_a_line` |
| `ETH3D_REF` | 26 帧 MVSNet 输入所在的 run 目录 | `$ETH3D_LINE/run_20260824` |
| `ARM_TOOLS` | `run_arm.py` / `fuse_arm.py` 所在目录 | `…/experiments/mvs_pose_ablation_2026-08-18/tools` |
| `REGION_METRIC` | `region_metrics.py` + `cache/` + `viz/` + `logs/` | `$ETH3D_LINE/region_metric_20260824` |
| `PACK` | 弹药包自身(`eval_ckpt.sh` 默认取自己所在目录) | 脚本所在目录 |
| `MVS_IN` | 26 帧输入(仅 `noise_floor.sh`) | `$ETH3D_REF/mvs_office` |

例:

```bash
PY=python3 DIFFMVS_REPO=/root/diffmvs ETH3D_LINE=/data/eth3d \
ARM_TOOLS=/data/finetune_pack/vendored REGION_METRIC=/data/region_metric \
bash /data/finetune_pack/eval_ckpt.sh --ckpt /data/runs_tgmix/train_tg20/model_00000003.ckpt --tag tg20
```

## 附录 D:臂 C(Prism 式蒸馏)—— **本次不做,配方存档**

用户已拍板本次**不跑** C。这里只留下"如果以后要做,要先解决什么",
免得下次又从零开始想。

**想法**:不给白墙"真值深度",而是给它一个**更强的老师**在同一批白墙帧上的输出,
让学生在无纹理区去拟合老师的深度/法向,而不是去拟合光度一致性
(白墙上光度一致性本来就退化 —— 这正是鬼墙的根)。

**为什么这次不做(三个未解决的前提)**:

1. **老师是谁没定。** 要么是更大的 MVS 模型,要么是单目深度先验。
   但项目铁律 [[feedback-never-use-lidar]] 与"深度先验只许四端皆有来源"
   把候选压得很窄 —— **选型本身就是一场调研,不是一个开关**。
2. **蒸馏要改损失函数。** `train.py` 的 `compute_inverse_loss` 是官方件,
   加蒸馏项 = 动损失函数。项目里"改损失函数需用户重新拍板"是明文规矩
   (见 `project_pocketworld_ghost_wall_and_zerodtu_retrain.md` 的"后手"一节)。
3. **TG 已经有真值深度。** 白墙帧的 GT 深度是渲染出来的,精确。
   在**已经有真值**的数据上做蒸馏,收益路径不清楚 —— 蒸馏的典型价值是
   "无真值域上迁移",而 TG 恰恰不是那种情况。
   ⇒ 真要做蒸馏,对象应该是**手机拍的真实白墙**(无真值),不是 TG。

**所以正确的顺序是**:先让臂 B 回答"有真值的白墙监督到底有没有用"。
- B 有用 ⇒ 说明白墙监督这条路通,那时再讨论"手机域无真值白墙怎么办"(蒸馏才有位置);
- B 没用 ⇒ 蒸馏更没有理由,因为连最干净的白墙监督都没能改善墙区。

**本次不需要为 C 准备任何东西。**

## 补遗(协调者 08-25):判决腿 2 的 TSDF 对比页脚本位置

弹药包制备时未找到 b28 TSDF 页的生成代码 —— 它不在 `_host_experiments/` 或 research-benchmarks,在:
`/Users/kaidongwang/Developer/tsdf_mvgZeroDTU_20260824/{run_tsdf.py, export_mesh_bins.py, render_screenshots.py}`
用法:新 ckpt 推理(run_arm.py, mvs_P16k 输入)→ `run_tsdf.py`(6mm 体素,官方 filter 门)→ `export_mesh_bins.py` 出 pos/col/idx → 拷入 `verdict_page/tsdf_<tag>/bin` 并复制 index.html 改 META 键。清理版(必须步骤,用户拍板):`~/Developer/tsdf_mvgZeroDTU_20260824/clean_mesh.py` 同参数照抄。
判决腿 2 至此闭合。

## 补遗 2(协调者 08-25):ckpt 防拿错断言

`casdiffmvs_blend.ckpt` 与 `casdiffmvs_blendmvg.ckpt` 同字节数(11,765,943),仅凭大小无法区分。脚本引用 blendmvg 基线前先断言:
```
[ "$(md5 -q .../casdiffmvs_blendmvg.ckpt)" = "f82d0030dbdb50dd83a2572542996f77" ] || { echo '🔴 ckpt 不对'; exit 1; }
```
