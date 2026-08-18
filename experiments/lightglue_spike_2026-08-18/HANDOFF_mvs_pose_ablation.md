# 任务:@16384 vs @8192 的位姿,对 CasDiffMVS 稠密结果到底有没有影响

## 背景(为什么做这个)

上游 SfM 前端(ALIKED+LightGlue)的关键点预算从 8192 抬到 16384,稀疏点多了 79%
(133,228 → 238,545)。问题是:**这对最终的稠密重建有没有用?**

已经查实(源码 `tools/python/diffmvs/colmap_input.py`):**CasDiffMVS 看不到点云**。
SfM 只通过三条通道影响它:

| 通道 | 出处 |
|---|---|
| 位姿 + 内参 | 直接取 extrinsic |
| depth_min/max | 该视图可见稀疏点深度的 1%/99% 分位(`colmap_input.py:368-371`) |
| pair.txt(选源视图) | 共视稀疏点三角化角套 `theta0=5°` 高斯求和,取 top-10(`:374-390, :417-418`) |

已经用代理指标量过这三条通道(2026-08-18):

```
                      噪声地板(同预算)   预算效应(16384 vs 8192)   倍数
光心偏差 中位            0.034%              0.074%              2.2×
朝向偏差 中位            0.0238°             0.0463°             1.9×
depth_max 中位           0.43%               1.36%               3.2×
depth_max p95            5.95%              15.84%              2.7×
源视图 top-10 完全一致   117/132             76/132               —
```

结论卡在这:**预算确实动了下游输入,幅度约为运行噪声的 2–3 倍,但方向是随机的**
(depth_max 有符号差:16384 更远的视图只占 38%,depth_min 精确 50:50)。
没有位姿真值,所以「不同」和「更好」区分不了。

**唯一能定论的就是这个任务:两套位姿各跑一遍 CasDiffMVS,比稠密结果。**

---

## 判据(按重要性排序)

用户的第一优先级是**场景覆盖范围**,不是点数。判据依次是:

1. **肉眼**(最终判据,不可省)——真彩 PLY 并排页,用户亲自看
2. **覆盖**——固定体素尺寸下的占据格子数(0.02/0.05/0.1/0.2 m 四档)
3. **表面粗糙度**——局部 PCA 最小特征值开方 = 邻域沿法线的 RMS 宽度
4. 点数

> ⚠️ **不要报 `<1%` 精度**。那个指标需要深度真值,只在 DTU/BlendedMVS 这类带 GT 的
> fixture 上有意义。本任务用的 b28 是真实拍摄,**没有 GT**。而且历史教训:
> `<1%` 只在稀疏 SfM 点上测,对白墙、地板等无纹理区是**结构性盲区**——曾经出现过
> 指标好看但肉眼明显更差的情况,最后是肉眼推翻了指标。

---

## 🔴 最重要的一条:必须先测噪声地板

**CasDiffMVS 的推理不可复现**——扩散噪声导致同样输入两次跑,21.5% 的像素深度差 >1%。

所以**任何两条臂之间的差异,在拿到噪声地板之前都是不可解释的**。必须:

- **方案 A(首选)**:把噪声做成**图输入**并固定,两条臂喂完全相同的噪声张量。
  (2026-08-17 的 ONNX 移植已经做过这件事,并验证过与内部 `randn_like` 逐比特相同,
  可以参考 `experiments/casdiffmvs_wgsl_port_2026-08-17/`)
- **方案 B(兜底)**:同一套位姿(P16k)跑两遍,得到的差异就是噪声地板。
  然后 P16k vs P8k 的差异必须**显著大于**这个地板才算数。

**两个方案至少做一个。跳过这一步的结果我们不会采信。**

---

## 现有资产(全部已核实存在,不要重新找)

### 租的 5090 机器(数据都在这)
```
ssh -p 43181 root@75.152.94.140
工作目录 /workspace/lgspike
  frames/              132 张 4032×3024 JPG(原始拍摄帧)
  work_P16k/sparse/0   @16384 的 COLMAP 重建(132/132 注册,238,545 点)
  work_P8k/sparse/0    @8192  的 COLMAP 重建(132/132 注册,133,228 点)
  work_P16kH/sparse/0  @16384 + fp16 匹配器(用于噪声地板对照,与 P16k 几乎同一朵云)
盘 916G 可用,GPU RTX 5090 32GB
```

> ⚠️ **`/workspace` 下有约 59GB 的别人的 DiffMVS 训练产物,绝对不要动、不要删。**
> 只在 `/workspace/lgspike/` 里干活。

### 本地研究仓
```
~/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs/
  colmap_input.py                    COLMAP → MVS 输入的官方桥(cameras/pair.txt/depth range)
  test.py                            推理入口
  filter.py                          🔴 官方融合,必须原样用
  models/                            网络定义
  checkpoints_unz/
    casdiffmvs_blendmvg.ckpt         ← 用这个(纯 BlendedMVS 训练,许可最干净)
    casdiffmvs_blend.ckpt
    casdiffmvs_dtu.ckpt
```

---

## 生产基线口径(必须照抄,这是已定案的)

```
分辨率      768 × 576  (4:3)
num_view    10          ← 不是 5,不是 7
filter.py   官方原版,参数:
              geo_mask_thres  = 3
              geo_pixel_thres = 1.0
              geo_depth_thres = 0.01
              photo_thres     = [0.3, 0.5, 0.5]   ← 三阶段 AND,不是只用末阶段
              深度平均         ← 官方有这一步,不要省
```

> 🔴 **历史事故(2026-08-17)**:上一轮有人没用仓库自带的 `filter.py`,自己写了融合,
> 结果四处偏离官方(num_view 用了 5/7、photo_thres 只存末阶段、漏了深度平均、
> 还混进了别的管线的法向/边缘门——**官方根本没有那两道门**)。表现出来是
> 「conf≥0.5 只滤掉 12%」这种怪现象,排查了很久。
> **先 100% 复刻官方,再谈任何改动。**

---

## 步骤

1. **准备**:把 diffmvs 整套 + 选定的 ckpt 传到 5090 机器的 `/workspace/lgspike/mvs/`。
   建独立 venv,别污染现有的 `/venv/main` 和 `venv_colmap`。

2. **生成 MVS 输入**(两套,唯一变量是重建目录):
   ```
   python colmap_input.py --input_folder <work_P16k 的父级布局> --output_folder mvs_in_P16k ...
   python colmap_input.py --input_folder <work_P8k  的父级布局> --output_folder mvs_in_P8k  ...
   ```
   ⚠️ `colmap_input.py` 期望 `<input_folder>/sparse/` 下直接是模型文件,而我们的布局是
   `work_X/sparse/0/`。要么加一层软链,要么改路径参数——**别改脚本逻辑**。
   生成后**必须核对**:两套的 `pair.txt` 每行都是 10 个源视图,`depth_ranges` 有 132 行。

3. **推理**(两套,同一 ckpt、同一分辨率、同一噪声):
   跑 `test.py`,输出深度图 + confidence。**记录每套的耗时**。

4. **融合**:官方 `filter.py`,参数如上。得到两朵稠密 PLY。

5. **噪声地板**:按上面「最重要的一条」做 A 或 B。

6. **度量**(脚本已存在,直接用,别重写):
   ```
   /workspace/lgspike/coverage_metric.py    覆盖(四档体素)+ kNN 间距
   /workspace/lgspike/local_roughness.py    表面粗糙度(局部 PCA,k=15)
   /workspace/lgspike/export_ply.py         真彩导出 + Umeyama gauge 对齐
   ```
   ⚠️ **比覆盖之前必须先 gauge 对齐**:两套重建的尺度/朝向/原点是各自任意的,
   `export_ply.py` 用相机光心做相似变换对齐(保形,云内几何不动)。
   对齐后报一下残差中位数——今天 P16k vs P8k 是 4.8mm,P16k vs P16kH 是 2.2mm,
   如果你的数字远大于这个量级,说明哪里错了。

7. **出并排页**:`/workspace/lgspike/build_local_page.py` 已支持 `ply:` 直读 PLY,
   加一组 SETS 即可。**页面必须是自包含的单个 HTML(数据 base64 内嵌),
   能在本地双击打开** —— 不要做成需要起服务器或依赖 CDN 的版本。

---

## 交付物

1. **并排真彩 PLY 页面**(自包含 HTML),窗口:
   `P16k 稠密` / `P8k 稠密` / `噪声地板对照`
2. 一张表:点数、覆盖(四档)、粗糙度、推理耗时,**并列出噪声地板**
3. 一句话结论:**预算 8192→16384 对稠密结果的影响,是否显著超出噪声地板?**
4. 所有脚本 + README 提交到研究仓
   `~/Developer/Aether3D-cross/pocketworld_research_benchmarks/experiments/`
   下新建目录,命名 `mvs_pose_ablation_2026-08-18`

---

## 已知的坑(都是踩过的)

- **`pkill -f xxx` / `pgrep -f xxx` 会自匹配**:命令行自身含该字符串,会杀掉自己的父 shell。
  今天因此浪费过三次。用 `pgrep -f "[x]xx"` 这种写法,或干脆按 PID。
- **`devicectl`/`scp` 拉取可能中断且只丢一部分**:拉完必须逐文件对账,别看 rc=0 就信。
- **不要用 heredoc 往远程写 Python**:引号会被层层 shell 吃掉。本地写好 `scp` 上去。
- **`torch.profiler` 的输出经 `| tail` 会被缓冲**:长任务要 `-u` 且重定向到文件再 poll。
- **推理不可复现**已在上面强调,这里再说一遍:**没有噪声地板的结论一律不采信。**
- **报告耗时要分环节**:今天发现建图耗时是匹配的 16 倍,如果只报总时长会掩盖真实瓶颈。

---

## 这个实验会改变什么决策

- 如果 **P16k 显著优于 P8k**(超出噪声地板):@16384 的 2× 算力对最终成品是值的,
  端上必须想办法扛住这个预算。
- 如果 **两者无显著差异**:@16384 的价值只在**用户拍摄期看到的预览云覆盖**上。
  那么预览和成品应该拆成两笔预算——预览可以追覆盖,成品用低预算位姿即可,
  端上算力压力立刻减半。

这两条路的工程后果完全相反,所以这个实验值得做扎实。
