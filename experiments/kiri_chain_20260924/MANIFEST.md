# 大文件清单(不入库)

## 本地

| 内容 | 位置 | 大小 |
|---|---|---|
| 输入 132 张照片 + 相机 + pair.txt | `~/Documents/progecttwo/_host_experiments.nosync/pose_ablation_20260818/mvs_P16k/` | 128 MB |
| CasDiffMVS full_ep0 权重 | `~/Developer/casdiff_full_ckpts/full_ep0.ckpt`(md5 e71dc850478eaf937b0f956d92a2814b) | 11.8 MB |

## 旧箱 107.209.104.125:45434(09-24 起离线,数据仍在主机上)

| 内容 | 路径 | 大小 |
|---|---|---|
| 逐视图过滤后深度缓存 | `/root/tsdf_improve/four/cache/*.npz` + `order.json` | — |
| KIRI 网格 | `/root/tsdf_improve/kiri/out/kiri_v0.01_t0.04_w5.ply` 等 | — |
| 贴图结果(默认) | `/root/tsdf_improve/tex_K1/K1_textured.{obj,mtl,glb}` + 217 PNG | GLB 197.9 MB |
| 贴图结果(保留未见面) | `/root/tsdf_improve/tex_K1/K1keep_textured.*` | GLB 224.2 MB |
| VGGT 原样点云 | `/root/page_cmp/vggt_raw/all_points_conf0.glb` | 429.0 MB |
| 对比网页与分块 | `/root/page_cmp/` | — |

## 可重算

以上旧箱产物都可以用本目录脚本从本地输入重算。VGGT-1B-Commercial 权重是 gated 的,需要用户自己的 HF token 重新下载。
