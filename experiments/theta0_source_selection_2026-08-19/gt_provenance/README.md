# BlendedMVS 真值可信度 + 合成数据集许可(2026-08-19/20)

## ① 假设:"BlendedMVS 的真值在无纹理区本身就是错的" —— ⚰️ 推翻

### 假设怎么来的

BlendedMVS 官方流程(CVPR 2020 原文 + 官方 README 证实):
**用商业 MVS 管线(Altizure)从照片重建带纹理网格 → 把网格渲染成图和深度图。**
目录名直白:`rendered_depth_maps`。

⇒ **"真值"本身就是 MVS 的输出。** 而我们的病灶恰恰是 MVS 在无纹理区自信地算错。
推论:网络只是学会复现真值里的错误 ⇒ 换更大的 BlendedMVG 无用(错误只是更多份)。

**这个推论若成立,08-23 那次重训注定失败。所以必须先验。**

### 怎么验的

⚠️ 渲染深度每像素只有一层,不会出现稠密云那种"第二面墙",所以不能直接找鬼层。
判据换成:**同一场景、同一平面上,真值在低纹理像素处是不是比高纹理像素更不平?**
同一平面 ⇒ 几何被控住,唯一差别是纹理。

工具 `tools/gt_texture_bias.py`:真值深度反投影 → RANSAC 找最大平面 →
用图像局部梯度(Sobel + 15×15 均值)把平面上的像素分低/高纹理两组(25%/75% 分位)→ 比残差。

### 结果

| | 低纹理 | 高纹理 | 倍数 |
|---|---|---|---|
| 到平面残差 p50 | **11.31mm** | **11.46mm** | **0.99×** |
| 到平面残差 p90 | 46.95mm | 43.06mm | 1.09× |

**低纹理更差的帧:7/19(37%)—— 基本是抛硬币。**

⇒ **假设推翻。BlendedMVS 的真值在无纹理区并不比有纹理区差。**

旁证:四方对照里 `blendmvg`(MVS 渲染真值最多的那个)恰恰是**唯一没有鬼层**的。
若真值有毒,它该最差。**数据自洽,是推论错了。**

⚠️ 样本 19 帧 / 4 场景。够推翻"系统性差异"(0.99 离 1.0 太近),
**不够断言"绝对干净"**。要加强可扩到几百帧,但 0.99 不会因样本变多变成 2。

## ② 合成室内数据集许可调研

动机:如果最后需要"仿造 DTU"(其价值在**真值在无纹理区也准** —— 结构光主动测量,
不像 BlendedMVS 那样源自 MVS),合成渲染是最便宜的路,但**许可是我们踩过的坑**。

| 数据集 | 许可 | 可商用 |
|---|---|---|
| **TartanAir / TartanGround** | **CC BY 4.0** | **✅(需署名)** |
| Hypersim(Apple) | CC BY-SA 3.0 + **非商业科研**自定义条款 | ❌ |
| Replica(Meta) | 明文 non-commercial / not-for-profit | ❌ |
| 3D-FRONT | 学术免费,商用条款未查到 | ⚠️ 待定 |
| InteriorNet | 未查到 | ⚠️ 待定 |

🔴 **这几条是 WebSearch 得来的,不是逐字读 LICENSE 原文。**
按 DTU 那次的教训,**上线前必须有人打开 LICENSE 逐字核** ——
尤其 Hypersim "CC BY-SA 3.0 + 非商业条款"的组合看着自相矛盾。

### ⚠️ 对这条路的保留

**TartanGround 是合成的,DTU 是真实拍摄。** 我们的病灶出在**真实手机照片的无纹理白墙**上;
合成白墙与真实白墙在噪声、光照、传感器特性上完全不同。
**"合成数据能替代 DTU"本身是未验证的假设。**

⇒ 建议 **08-23 先看零DTU+BlendedMVG 的结果**,那一格填上才知道还缺什么。
现在造数据 = 在前一个实验出结果前加码。

**Sources**: [BlendedMVS CVPR 2020](https://openaccess.thecvf.com/content_CVPR_2020/papers/Yao_BlendedMVS_A_Large-Scale_Dataset_for_Generalized_Multi-View_Stereo_Networks_CVPR_2020_paper.pdf) ·
[ml-hypersim LICENSE](https://github.com/apple/ml-hypersim/blob/main/LICENSE.txt) ·
[Replica LICENSE](https://github.com/facebookresearch/Replica-Dataset/blob/main/LICENSE) ·
[TartanAir](https://tartanair.org/)
