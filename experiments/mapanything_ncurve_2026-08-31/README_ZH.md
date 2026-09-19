# MapAnything 在 Mac 上的复刻尝试 + N 曲线(2026-08-31)

**这条线已判死。** 本目录是 2026-09-19 从本机 `~/Developer/mapanything-ncurve-20260831/`(6.1 GB)
抢救出来的**全部非数据产物**(58 个文件 / 0.6 MB);数据部分当天删除,见文末"已删除与如何再生"。

## 判决

2026-08-31 的目标是**在 Mac 上复刻用户此前在 5090 上跑到的 MapAnything 质量**,**未达成**。
七个假设逐一实测否决(别再重试):

| 假设 | 否决证据 |
|---|---|
| 分块(K=8/4)导致 | 官方 132 帧全量一次前向,同样是雾 |
| 灰度输入 | 换真彩 2000×1500 后归一化密度不变 |
| fp16 精度 | fp32/fp16/bf16 归一化密度 64.0/64.3/64.3,完全一致 |
| 置信度过滤不足 | 过滤只减点数,**不改变归一化密度** |
| 复刻有 bug | 与 08-26 产物尺度归一后差 **1.1%** |
| 模型大小 giant vs v1 | 32 视图下归一化密度 27.33M vs 28.91M,差 5.8% |
| MPS 后端有缺陷 | CPU vs MPS 深度中位相对差 **0.0004%**,p99 0.001% |

🔴 **当时犯的最大方法错误**:拿未归一化的量做质量判断,一度得出"密度低 6.4 倍"——
实际 6.40 = 尺寸比 1.85 的立方,纯粹是全局尺度不同的假象。
**比较点云质量前必须先按 p5–p95 对角归一化。**

后续 2026-09-03 定了重影根因:**第一破坏层 = 模型自己预测的射线/内参**
(预测 fx / COLMAP fx = 0.768,单视图即错;喂 K 不被跟随、喂 pose 被跟随;
换真 K/真 pose 反而更差 ⇒ depth/K/pose 是围绕错误相机模型共适应的一套)。
详见 `experiments/mapanything_casdiffmvs_ghosting_2026-09-03/`。

## 唯一的定量产物:N 曲线(`results/ncurve_result.json`)

`facebook/map-anything-apache`,563.3 M 参数,torch 2.13.0,MPS(上限 13.32 GiB),
输入 1×3×392×518:

| N(视图数) | 秒 | 峰值显存 GiB |
|---:|---:|---:|
| 1 | 1.256 | 3.123 |
| 2 | 1.045 | 3.123 |
| 4 | 1.836 | 3.123 |
| 8 | 3.704 | 4.139 |
| 16 | 8.276 | 4.162 |
| 24 | 13.931 | 5.194 |
| 32 | 21.345 | 5.312 |
| 48 | 39.847 | 7.375 |

⇒ 时间随 N **超线性**(48 视图 = 单视图的 31.7 倍时间,而不是 48 倍线性也不是常数),
显存 3.1 → 7.4 GiB。48 视图已用掉 MPS 可用显存的 55%,132 视图全量在 Mac 上不可行——
这就是当时改走分块的原因,而分块被上表第一行否决(不是雾的成因)。

## 目录内容

```
scripts/                 4 个 .sh(取权重 / 下 giant / 在 5090 上跑 / 看门狗)
scripts/selfmade_deleted/  约 30 个 .py —— 原目录里已标记"自研、已弃用"的探针脚本,
                           按「禁止自研」铁律不再作为方案来源, 仅存档备查
logs/                    18 个 .log(ncurve / sweep / qual_k{2,4,8,full132} / fetch / official …)
results/                 ncurve_result.json + ma_config{,_v1}.json
```

## 已删除与如何再生(2026-09-19)

| 删掉的 | 大小 | 怎么再生 |
|---|---:|---|
| `weights/` | 2.2 G | HuggingFace 重新下载,`scripts/fetch_weights.sh` / `dl_giant.sh` |
| `ply/` | 1.3 G | 跑推理再生 |
| `web/` | 547 M | 判决页 bins,可由 ply 再生 |
| `imgs12mp_up` / `images_rgb` / `images` | 490 M | 来自那 132 张原始拍摄,原件另存 |
| `repo/` | 18 M | `git clone` 上游 mapanything |
| `.venv/` | — | 重建 |

相关记忆:`project_pocketworld_mapanything_repro_deadend_20260831`、
`project_pocketworld_mapanything_ghosting_root_cause_20260903`、
`project_pocketworld_dense_route_mapanything_verdict`。
