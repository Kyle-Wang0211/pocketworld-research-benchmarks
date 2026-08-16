# CasDiffMVS 从头训 BlendedMVG —— 上机前准备件

日期:2026-08-16
目的:**去掉 DTU 血统**。官方三个权重(dtu / blend / blendmvg)全部从 DTU 预训练来,
而 DTU **没有任何许可声明**(只有一句 citeware)⇒ 不能出货。
BlendedMVG 是 **CC BY 4.0**,干净。

目标产物:一个纯 BlendedMVG 训出来的 `casdiffmvs` 权重,并用**现有 138 帧真值对比台**
量出它相对官方权重掉了多少 / 涨了多少。

> 🔴 **这次实验回答的是一个我们一直没回答的问题。**
> 之前"CasDiffMVS <1% 精度 91.5%,赢 APDe 的 86.9%"这个结论,
> 用的是 **ofull15 调优档 + 带 DTU 血统、不能出货的权重**。
> **能出货的那个模型精度是多少,至今空白。** 这次就是去填它。

---

## 0. 一句话结论:这不是赌博,是一次有明确读数的实验

跑完直接接现有对比台,出 `<1%` / `<5%` / 覆盖率三个数,与下表并排:

| | 覆盖 | <1% | <5% | 备注 |
|---|---|---|---|---|
| APDe 完整流水 | 48.0% | 86.9% | 98.9% | ⚰️ 已因专利封存 |
| APDe 两遍简版 | 49.3% | 86.9% | 99.2% | 同上 |
| CasDiffMVS **base** | 51.0% | 82.7% | 99.7% | 带 DTU 血统 |
| CasDiffMVS **ofull15** | 51.6% | **91.5%** | 99.7% | 带 DTU 血统 |
| **本次:BlendedMVG 从头训** | ? | **?** | ? | ⬅️ 要填的格子 |

判据建议(用户签):只要 `<5%` 不低于 99.0%,且 `<1%` 不低于 base 档的 82.7%,
就算"重训可用",因为那样它仍不差于我们已经接受过的档位,而且**血统全干净**。

---

## 1. 官方配方的真实结构(从源码读的,不是从论文猜的)

`scripts/train/train_casdiffmvs.sh` 是**三段**,不是三个独立训练:

| 段 | 数据 | epochs | loadckpt | `--scale` | `--trainviews` |
|---|---|---|---|---|---|
| 1 | DTU | `--epochs=16` | 无(从头) | `0 0.5 0.1` | 5 |
| 2 | BlendedMVS | `--epochs=16 --train_epochs=8` | DTU 的 `model_000015` | `0 0.25 0.05` | 9 |
| 3 | BlendedMVS | `--epochs=16 --resume` | — | `0 0.125 0.025` | 9 |

### 🔑 两个只有读代码才看得出来的点

**(a) 第 2/3 段其实是一条连续的 16-epoch OneCycle,被劈成两次调用。**

`train.py:372` 建 scheduler 用的是 `len(loader) * args.epochs + 100`,两段都传 `--epochs=16`;
第 3 段 `--resume` 时 `last_epoch = len(loader)*start_epoch - 1`(`:371`)。
所以 LR 曲线是**连续的一条**。劈成两次调用的**唯一理由是中途要换 `--scale`**。

⇒ 从头训的正确对应物是:**一条 16-epoch OneCycle,在第 8 轮切换 scale**,
不是"训 8 轮再训 8 轮"。

**(b) `--scale`(扩散噪声尺度)是一条课程,不是常数。**

```
stage2 分量:  0.5  →  0.25  →  0.125
stage3 分量:  0.1  →  0.05  →  0.025
             (DTU)  (Blend)  (Blend resume)
```

**丢掉 DTU 段 = 跳过课程的第一档。** 这是从头训最可能出问题的地方,
所以下面的配置里专门有一个轴测它。

**(c) 官方自己说 BlendedMVG 不用改超参。**
README 第 26 行(2025-09-11):
> "we finetune it on **BlendedMVG** … The performance on benchmarks consistently improves
> **without changing other hyper-parameters**."(ETH3D Test 85.99 vs 85.11)

⚠️ 但那是**微调 DTU 预训练模型**的结论,**不能直接外推到从头训**。

---

## 2. 必须动的东西(逐条,含出处)

| # | 位置 | 官方 | 改成 | 为什么 |
|---|---|---|---|---|
| 1 | `--loadckpt` | DTU ckpt | **不传** | `train.py:45` 默认 `None`,`:338` 是 `elif` ⇒ 不传即从头训。**这是整件事的开关** |
| 2 | `--trainlist` | `lists/blend/train.txt`(**106 场景 = BlendedMVS**) | 段①**沿用它**;段②换自建 MVG 清单 | 🔴 **仓库里没有 BlendedMVG 清单**(BlendedMVS 是 MVG 的子集),见 `tools/make_blendmvg_list.py` |
| 3 | `train.py:358,360` `num_workers=8` | 硬编码 | **提到 16–24** | 9 视图 × JPEG 解码 = 每 batch 36 次解码。**H100 上这是头号瓶颈**,不改等于租了张闲卡 |
| 4 | `--scale` 起点 | `0 0.25 0.05` | 配置轴(见 §3) | 丢了 DTU 段就丢了 `0 0.5 0.1` 那一档课程 |
| 5 | `--epochs` | 16 | 配置轴 | 从头训没有 DTU 打底,大概率需要更多轮 |
| 6 | `--conf_weight` | 脚本传 `0.05` | **保持 0.05** | ⚠️ argparse 默认是 `1.0`(`train.py:83`),**不显式传会差 20 倍** |

### ⚠️ 不要动的

- `--trainviews 9` / `--numdepth 384` / `--numdepth_initial 48` / 各 `*_dim` / `stage_iters`
  —— 动了就**不能和现有数字比**,而这次实验的全部价值就在可比性。
- 别加混合精度(AMP)。它改数值、可能让本来就不稳的从头训发散。
  真要加,当成第 5 个配置单独跑,别混进主线。

---

## 3. 四个并发配置(单卡 H100 80GB 上同时跑)

设计原则:**四个配置各自消灭一个不确定性**,而不是随机撒点。

| 配置 | epochs | scale 课程 | lr | 消灭哪个不确定性 |
|---|---|---|---|---|
| **A 基准** | 16(第8轮切) | `0 0.25 0.05` → `0 0.125 0.025` | 0.001 | 官方 blend 配方原样搬到从头训。**对照组** |
| **B 全课程** | 24(第8/16轮切) | `0 0.5 0.1` → `0 0.25 0.05` → `0 0.125 0.025` | 0.001 | 把 DTU 段的噪声课程**在 BlendedMVG 上补回来** |
| **C 长训** | 32(第16轮切) | 同 A | 0.001 | 「从头训只是需要更多轮」这个假设 |
| **D 低 LR** | 24(第12轮切) | 同 A | 0.0005 | 「从头训 onecycle 峰值过高会发散」这个假设 |

**B 是我最看好的那个** —— 它是唯一在结构上补偿了"丢掉 DTU 段"的配置。

---

## 3.5 🔴 两段式:别把四个配置直接铺在全量 BlendedMVG 上

粗估四配置全铺在 BlendedMVG 上是**天级不是小时级**(见 §4.5)。改成两段:

| 段 | 数据 | 做什么 | 为什么 |
|---|---|---|---|
| **①** | **BlendedMVS**(106 场景,仓库自带清单) | 四配置从头训,选赢家 | **单变量**:只变"有没有 DTU 预训练",数据集与官方 blend 段**完全同一份** ⇒ 数字能直接和官方权重对比 |
| **②** | **全量 BlendedMVG** | 赢家权重**微调** | 结构与官方新权重平行 |

### 段②是微调不是从头训 —— 这是省时间的关键

```
官方新权重:  DTU        → 微调 BlendedMVG
我们:        BlendedMVS → 微调 BlendedMVG    ← 同一结构,DTU 换成 BlendedMVS
```

两份数据都是 **CC BY 4.0** ⇒ 全程零 DTU,血统干净。
官方对 BlendedMVG 微调的原话是「without changing other hyper-parameters」,
所以段②直接用官方 blend 段的末档参数,不另外发明。

⚠️ **别在段①就用全量 MVG** —— 那会同时变"没有 DTU 预训练"和"换了数据集"**两个变量**,
出了问题分不清是哪个造成的。

## 4. 上机执行顺序(别一上来就四个齐发)

```
① 环境 + 补丁                     tools/prep_h100.sh
② 🔴 pilot 单进程跑 1 轮           量 it/s 与显存 —— 决定能并发几个、真实要多久
③ 段①:BlendedMVS 上并发四配置    TIER=mvs  ./train_blendmvg_scratch.sh A B C D
④ 四个 ckpt 各接对比台,选赢家     tools/install_new_ckpt.py
⑤ 建 BlendedMVG 清单              tools/make_blendmvg_list.py
⑥ 段②:赢家微调全量 MVG          TIER=mvg  ./train_blendmvg_scratch.sh finetune:B
⑦ 再接一次对比台                  tools/install_new_ckpt.py
```

## 4.5 时长:我只能给带推导的区间,真数要 pilot 给

```
小时数 =(样本数 ÷ batch 4)× 轮数 × 每 iter 秒数 ÷ 3600
```

三个量里**只有轮数是确切的**(A=16 / B=24 / C=32 / D=24)。

粗估(⚠️ 估算叠估算,误差可能好几倍,**不要按它预付机时**):
- 配置 A 单跑在**全量 BlendedMVG** 上 ≈ 14–42 小时
- 四配置全铺在 BlendedMVG 上 ≈ **1.5–4.5 天** ← 这就是为什么要两段式
- 段①在 BlendedMVS 上约为其 **1/3**

**pilot 跑完这一整节作废**:`time=` 给每 iter 秒数,
日志开头 `dataset train metas:` 给样本数,代进上面算式即可。
⇒ **按小时租,pilot 完再决定包多久。**

### 🔴 第 ③ 步不能跳

MVS 的显存大头是 **cost volume 不是权重**(模型只有 0.925M 参数),
**按参数量估显存一定错**。必须实测单进程占多少,再决定开 3 个还是 4 个。

这一小时省下来的是:要么保守只跑 1 个(浪费整张卡),要么开太多 OOM(浪费更多)。

---

## 5. 机器规格(GPU 不是最容易翻车的地方)

| | 要求 | 不满足会怎样 |
|---|---|---|
| GPU | **H100 80GB** 或 A100 **80GB** | 40GB 版本并发不了,单卡优势全没 |
| vCPU | **≥ 64** | 🔴 9 视图 JPEG 解码是纯 CPU 活,**并发 N 个 = N 倍解码压力**,CPU 不够 = H100 空转 |
| 本地盘 | **NVMe ≥ 500GB** | BlendedMVG 比 BlendedMVS(约 27GB)大得多,**上机第一件事是核实实际体积**;挂网络盘会把 dataloader 拖死 |
| 内存 | ≥ 128GB | 并发 4 个 × 16–24 workers 的预取队列 |

---

## 6. 评测怎么接(零改动接现有对比台)

`tools/python/pw_diffmvs_common.py:66-77` 按环境变量选权重:

```python
dom = os.environ.get("AETHER_CKPT", "dtu")
assert dom in ("dtu", "blend", "blendmvg")
ckpt = CKPT_DIR / f"{method}_{dom}.ckpt"
```

⇒ 只需两步:
1. 把新权重放成 `checkpoints/casdiffmvs_mvgscratch.ckpt`
2. `pw_diffmvs_common.py:71` 的 assert 里加 `"mvgscratch"`(**一行**)

然后 `AETHER_CKPT=mvgscratch` 跑现有流程,与历史数字**同一把尺子**。

⚠️ 权重 key 集合必须与 blend 一致;`build_model` 用 `strict=False` 加载,
**key 对不上不会报错、只会静默用随机初始化**。
⇒ 用 `tools/install_new_ckpt.py` 装,别 `cp`。它逐 key 比对集合 + 形状,不过就拒绝安装。

**已实测该工具有效**:
- 正例 `casdiffmvs_blendmvg` vs `casdiffmvs_blend` → 784 key 全等,通过
- 反例 `diffmvs_blend` 冒充 → 抓到 **8 处形状不符**,拒绝。
  ⚠️ 注意这 8 个 key **名字完全相同**(如 `update_block.0.mask.2.weight`,
  36 vs 144 通道),`strict=False` 会静默放过 —— 这就是它存在的理由。

📌 记账:`casdiffmvs_*.ckpt` 的 state_dict 浮点数是 **1.385M**(含扩散调度 buffer),
不是我们一直引用的 0.925M(那是可训练参数口径)。两者都很小,但引用时要说明口径。

---

## 7. 并行跑着的零成本副本:向 DTU 要授权

发一封信给 DTU 作者(Henrik Aanæs / Anders Dahl)索书面许可。**零算力**,拿到则官方
ckpt 直接可用。但**回信时间不可控,不能当主路径** —— 让它和训练并行,回了就是白赚。

⚠️ 措辞要覆盖两件事,不是一件:
1. 可以使用该数据集
2. **可以用它训练模型并商业分发训练出的权重**

泛泛一句 "feel free to use it" 不覆盖第 2 条。且授权方需是有签字权的一方(DTU 的 KTO/法务),
不是教授个人邮件 —— 丹麦职务作品的著作权归属取决于雇佣合同,外部看不到。

---

## 8. 相关

- 许可地图:`project_pocketworld_mvs_license_map_and_apde`
- 专利 FTO(APDe 为何封存):`project_pocketworld_mvs_patent_fto`
- 138 帧对比台由来:`experiments/apde_wgsl_port_2026-08-14/`
