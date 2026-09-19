# TartanGround → CasDiffMVS 官方训练格式转换可行性验证报告

日期:2026-08-24
产物根目录:`/Users/kaidongwang/Developer/tartanground_b_line/`(未写入 `~/Documents`)

## 0. 结论先行

**可行。** 用真实下载的 TartanGround 子集(单环境 Office、单条轨迹 P0000、单相机
lcam_front,678 帧,~388MB 原始数据)跑通了完整链路:官方字段核查 → 转换成
CasDiffMVS 官方 BlendedMVS 训练格式(`datasets/blend.py::MVSDataset`)→ 官方
dataloader 真实 `__getitem__` → `casdiffmvs_mvgZeroDTU.ckpt` 真实前向推理,
**0 missing/0 unexpected 权重键,6 个 stage 输出 100% finite,深度值范围与
cam.txt 里的 depth_min/depth_max 同数量级**,无形状/单位爆炸。

共视分数(view-selection score)**没有自研**,逐字复刻官方公式,详见第 3 节。

---

## 1. 数据结构(官方原文出处)

### 1.1 下载方式

官方 Python 工具包 `tartanairpy`(`https://github.com/castacks/tartanairpy`,
本机浅克隆于 `/Users/kaidongwang/Developer/tartanground_b_line/tartanairpy`)提供:

```python
ta.download_ground(env=[...], version=['omni','diff','anymal'], traj=['P0000'],
                    modality=[...], camera_name=[...], unzip=True, ...)
```

原文出处:`tartanairpy/examples/download_ground_example.py`(本次任务直接读到的
官方示例脚本原文,作者 Manthan Patel,日期 2025-08-08)以及
`tartanairpy/tartanair/tartanair.py:161-190`(`download_ground` 函数签名与
docstring)。三种机器人版本 `omni/diff/anymal` 对应轨迹编号段
`P0000../P1000../P2000..`。

本次验证没有用 tartanairpy(它依赖 boto3/huggingface_hub 等重量级依赖,且要求
先 `ta.init(root)`),而是直接对 Hugging Face 数据集仓库的分块 zip 按需
`curl` 下载(见第 4 节)——这是被 `tartanairpy/tartanair/downloader.py` 内部
证实的同一套文件粒度(`{Env}/Data_{version}/P{nnnn}/{modality}_{camera}.zip`,
出处:`tartanairpy/tartanair/downloader.py:437-460` 的路径示例注释),只是跳过了
中间层 Python 封装,效果等价。

### 1.2 每帧提供的模态与命名

`tartanairpy/examples/download_ground_example.py` 注释原文列出的合法
modality 取值:
`['image', 'meta', 'depth', 'seg', 'lidar', 'imu', 'rosbag', 'sem_pcd', 'seg_labels', 'rgb_pcd']`,
camera_name 取值(12 路,6 组左右目):
`['lcam_front','lcam_right','lcam_left','lcam_back','lcam_top','lcam_bottom','rcam_front','rcam_right','rcam_left','rcam_back','rcam_top','rcam_bottom']`。

实测(Office/Data_omni/P0000)解压后目录:

```
image/image_lcam_front/{:06d}_lcam_front.png        # 640x640 RGB PNG, 678 张
depth/depth_lcam_front/{:06d}_lcam_front_depth.png   # 640x640 RGBA8 PNG(见1.4), 678 张
metadata/pose_lcam_front.txt                          # 678 行, 每行7个数
metadata/P0000_metadata.json                          # num_poses:678, 与轨迹长度吻合
metadata/collection_config.yaml                       # 12路相机名映射 + image_type 列表
```

`collection_config.yaml` 原文确认了 AirSim 的 3 种 image_type:
`Scene`(=image)、`DepthPlanar`(=depth)、`Segmentation`(=seg)——
**DepthPlanar 明确是"平面深度"(沿光轴的 z-depth),不是欧氏距离**,这与
1.4 节的解码结果自洽。

### 1.3 相机内参

官方仓库**没有**给出单独的内参 json/yaml,而是用固定假设:FOV=90°、光心在图像
中心的针孔模型,由分辨率现算。出处:
`tartanairpy/tartanair/reader.py` 的 `depth_to_dist()`(约 line 131、153):

> `assume: fov = 90 on both x and y axes, and optical center is at image center.`
> `f = ww/2`(`ww`=图像宽度)

实测图像分辨率 **640×640**(用 `PIL.Image.open` 直接测得,不是文档里
TartanAir V1 的 640×480——这点两者不同,已用真实文件验证,不是抄文档臆断)。
因此 `fx=fy=320, cx=320, cy=320`。

⚠️ 对照:`tartanair_tools/data_type.md`(TartanAir **V1**,而非 TartanGround)
原文给的是 `fx=fy=320.0, cx=320.0, cy=240.0, width=640, height=480`——这是
非方形 V1 的老数据,不能直接套用到 TartanGround,已在转换器里用**实测分辨率**
而非死抄文档数字。

### 1.4 深度格式与单位

`tartanair_tools/data_type.md` 原文(TartanAir V1 文档,描述的是 `.npy` 格式):
> "The depth maps are stored as 640x480 16-bit numpy array in NPY format... The
> unit of the depth value is meter."

但**实测 TartanGround 在 HuggingFace 上发布的深度文件是 PNG,不是 npy**
(`depth_lcam_front/000306_lcam_front_depth.png`,`cv2.IMREAD_UNCHANGED` 读出
是 640×640×4 的 `uint8` RGBA)。真正生效的解码路径是
`tartanairpy/tartanair/reader.py::read_depth()` 里 `.npy` 分支之外的
`else` 分支(约 line 58-65):

```python
depth_rgba = cv2.imread(depthpath, cv2.IMREAD_UNCHANGED)
depth = self.depth_rgba_float32(depth_rgba)   # depth_rgba.view("<f4")
```

即 4 个 uint8 通道按小端 bit-reinterpret 成一个 float32,单位仍是米(与
data_type.md 的米制单位说法一致,只是容器换成了 RGBA8-PNG 而不是 npy)。
实测(`000306_lcam_front_depth.png`)解码后 min=1.22m, max=18.59m,
mean=3.62m,数值在室内 Office 场景下完全合理。**这是本次转换器实际使用的
解码方式,已用真实文件验证,不是凭文档假设。**

### 1.5 Pose 文件格式与坐标系

`tartanair_tools/data_type.md` 原文:

> "The format of each line is 'tx ty tz qx qy qz qw'."
> "The camera motion is defined in the NED frame. That is to say, the x-axis
> is pointing to the camera's forward, the y-axis is pointing to the camera's
> right, the z-axis is pointing to the camera's downward."

实测 `pose_lcam_front.txt` 678 行、每行 7 个数,与 `P0000_metadata.json` 的
`"num_poses": 678` 完全吻合。**世界系也是 NED**(该文档同一节说明,x-N/y-E/z-D)。

⚠️ 这是本任务里最容易踩坑、也最容易被忽视的一环:NED 相机系(x-前 y-右 z-下)
和标准 CV/COLMAP 相机系(x-右 y-下 z-前)**不是同一个约定**,直接把
`[qx,qy,qz,qw]` 转成旋转矩阵塞进 cam.txt 的 extrinsic 会让整个投影链条错位
(z 不再是"前方深度")。官方转换函数详见第 2 节。

### 1.6 许可证

Hugging Face 官方 API(`https://huggingface.co/api/datasets/theairlabcmu/TartanGround`)
的 `cardData.license` 字段与 tag 均为 **`cc-by-4.0`**(CC BY 4.0,可商用,
仅需署名),已用 API 直接核实(非二手转述)。

---

## 2. NED → 标准 CV 相机系转换(官方复刻,非自研)

出处:`tartanair_tools/evaluation/trajectory_transform.py:21-35`
(本机克隆路径:`/Users/kaidongwang/Developer/tartanground_b_line/tartanair_tools/evaluation/trajectory_transform.py`),函数 `ned2cam`:

```python
def ned2cam(traj):
    T = np.array([[0,1,0,0],
                  [0,0,1,0],
                  [1,0,0,0],
                  [0,0,0,1]], dtype=np.float32)
    T_inv = np.linalg.inv(T)
    ...
    ttt = T.dot(tt).dot(T_inv)   # tt = pos_quats2SE_matrices(...)
```

`tartanair_tools/README.md:232` 原文进一步确认了这个约定:

> "Note that our camera poses are defined in the NED frame... You can use the
> `cam2ned` function in the `evaluation/trajectory_transform.py` to transform
> the trajectory from the camera frame to the NED frame."

转换器 `tartanground2mvsnet.py::ned_pose_to_cv_cam2world()` 对每一帧的
camera-to-world SE(3) 做同一个相似变换 `T @ SE_ned @ T^-1`,再取逆得到
world-to-camera 的 `extrinsic`(与 `colmap_input.py` 里 COLMAP 的
world-to-camera 约定一致,已用 `filter.py::reproject_with_depth` 的投影链
核对过量纲——见第 3 节的复用)。T 对整条轨迹的每一帧统一作用,只改变全局朝向
(纯旋转),不改变相机间相对基线/夹角,对 MVS 训练无影响。

---

## 3. 共视分数(view-selection score):官方算法出处 + 复刻方式

### 3.1 官方公式(找到且核实,未自研)

上游权威实现:**YoYo000/MVSNet** 仓库 `mvsnet/colmap2mvsnet.py::calc_score`
(2026-08-24 用 WebFetch 直接读取
`https://raw.githubusercontent.com/YoYo000/MVSNet/master/mvsnet/colmap2mvsnet.py`
核实的原文):

```python
score += np.exp(-(theta - args.theta0) * (theta - args.theta0) /
               (2 * (args.sigma1 if theta <= args.theta0 else args.sigma2) ** 2))
```
默认 `theta0=5°, sigma1=1, sigma2=10`。

本机训练仓库已经 vendor 了一份**逐字段等价**的实现(用户此前已验证与上游
输出完全一致,只做了 O(n²)→O(1) 的集合成员测试性能优化,不改变输出,见文件内
`[pw]` 风格注释):
`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs/colmap_input.py:374-397`
(`calc_score` 函数),默认参数
`colmap_input.py:251-253`:`theta0=5, sigma1=1, sigma2=10`,与上游逐字节一致。

### 3.2 TartanGround 没有 COLMAP 稀疏点——如何在不自研公式的前提下适配

`calc_score` 的角度-高斯打分公式本身**逐字保留、一个数没改**。唯一需要适配的
是公式输入——原始 `id_intersect`(两张图共同看到的 COLMAP 稀疏点 3D 坐标)
对 TartanGround 不存在,因为 TartanGround 给的是 GT 稠密深度而不是 COLMAP
重建。替代方案:用官方**已经在同一仓库里、用于测试期深度融合**的几何一致性
判据反投影,来确定"共视点集合",而不是发明新的判据:

`filter.py::reproject_with_depth` + `filter.py::check_geometric_consistency`
(`/Users/kaidongwang/Developer/Aether3D-cross/pocketworld_research_benchmarks/tools/python/diffmvs/filter.py:8-104`),
默认阈值原文:
```python
geo_pixel_thres=1.0,
geo_depth_thres=0.01,
...
mask = np.logical_and(dist < geo_pixel_thres, relative_depth_diff < geo_depth_thres)
```

转换器 `tartanground2mvsnet.py` 对每对视角 (i,j):
1. 用**逐字复刻**的 `reproject_with_depth`/`check_geometric_consistency`(阈值
   与官方完全相同,1.0px / 1% 相对深度差)找出 ref 图里"投到 src 再投回来
   仍然自洽"的像素掩码;
2. 把这些像素用 ref 视角自己的 GT 深度反投影成世界系 3D 点,作为
   `id_intersect` 的替代输入;
3. 对这些点跑**官方原样**的角度-高斯打分公式(`theta0=5,sigma1=1,sigma2=10`),
   求和得到 `score[i,j]`。

这是"复刻官方算法 + 换一种方式产生共视点集合",不是发明新的打分逻辑——报告
在此明确标注这一处适配,不冒充是官方对 TartanGround 的原装流程(官方论文没有
公开过 TartanGround 自己的 pair 生成脚本)。

pair.txt 写出格式(`%d\n%d ` + `id score id score ...`)逐字对齐
`colmap_input.py:447-451` 的官方写法。

---

## 4. 体积账

### 4.1 全量数据集(官方原文数字,两个口径有出入,如实两个都列)

- Hugging Face 数据集页(WebFetch 于 2026-08-24):**"Total file size: 17.9 TB"**
- TartanGround 论文(arXiv:2505.10696v2,III-A 节原文):
  **"total dataset size of approximately 15 TB, 1.44 million samples, and
  17.3 million RGB images"**

两个数字量级一致(15–17.9TB),差异可能来自论文发表后仓库又追加了模态/环境,
或统计口径不同(是否含 rosbag/lidar 等),本报告不猜测,只如实并列两个来源。

63 个环境、878 条轨迹(440 omni + 198 diff + 240 legged/anymal)、
每条轨迹 600–8000 帧,均出自同一节论文原文。

### 4.2 单条轨迹实测体积(本次真实下载,Office/Data_omni/P0000,678 帧)

| 文件 | 大小(字节, HF API 精确值) |
|---|---|
| `image_lcam_front.zip` | 294,416,291 (280.8 MB) |
| `depth_lcam_front.zip` | 92,514,768 (88.2 MB) |
| `metadata.zip`(12 路相机 pose + json + yaml) | 1,470,529 (1.4 MB) |
| **本次实际下载合计** | **388,401,588 (~370.4 MB)** |

单帧单相机 image+depth 合计 ≈ **0.5706 MB/帧**(=(294,416,291+92,514,768)/678)。

同一目录下**未下载**的其余模态体积对比(仅供体量感知,来自 HF API 目录树,
未下载):`lidar.zip` 433 MB、其余 11 路相机 image/depth 各在 15–110MB 区间、
`imu.zip` 5.7 MB、`seg_*` 各 2–8MB——12 路相机 + lidar + imu + seg 全模态
一条轨迹总量级在 3–4 GB,是本次只取单相机 image+depth 的 8–10 倍。

### 4.3 外推(必须租机下载,本机口径)

若训练只需 image+depth、单前视相机(与本次转换器路径一致的最小方案):
`0.5706 MB/帧 × 1,440,000 帧(论文口径样本数,已用 P0000 实测的
"678帧=678 samples" 核对过粒度是按帧而非按相机相乘)≈ 822 GB`。

若需要 12 路相机(6 组左右目)全部 image+depth(不含 lidar/imu/seg/rosbag):
`822 GB × 12 ≈ 9.85 TB`,与官方 15–17.9TB 的"全模态"总量级吻合(官方口径还
多了 seg/lidar/imu/rosbag/sem_pcd/seg_labels/rgb_pcd,比 image+depth 更大是
合理的)。

**结论:即使只要 image+depth 单相机,全量 TartanGround 也有 ~800GB 量级,
远超本机 79GB 可用空间和 15GB 预算上限,必须在租用机上下载/训练,本机只能
做子集验证。** 这与任务描述的预期一致。

---

## 5. 字段核查表

| 字段 | 官方文档/代码原文 | 实测核实 | 结论 |
|---|---|---|---|
| 图像分辨率 | V1 文档写 640×480(`data_type.md`);TartanGround 论文只说 FOV=90° 未给分辨率数字 | 实测 640×640(`PIL.Image.size`) | **以实测为准**,V1 文档数字不适用于 TartanGround |
| 深度容器格式 | V1 文档写 `.npy` | 实测 HF 上是 PNG(RGBA8 bit-reinterpret 成 float32) | **以实测为准**,走 `reader.py` 的 PNG 分支而非 npy 分支 |
| 深度含义 | `collection_config.yaml` 写 `DepthPlanar` | 数值范围 1.22–18.59m 与室内场景吻合 | z-depth(沿光轴),非欧氏距离 |
| 深度单位 | data_type.md: "unit... is meter" | 数值量级(米级家具/房间尺寸)吻合 | 米 |
| 内参 | `reader.py`: fov=90°,光心居中,`f=W/2` | 640×640 ⇒ fx=fy=320,cx=cy=320 | 用实测分辨率现算,不抄 V1 的 cx=320,cy=240 |
| Pose 格式 | `tx ty tz qx qy qz qw`,NED 世界系+NED 相机系 | 678 行与 `num_poses:678` 吻合 | 需 `ned2cam` 转换后才能当标准 CV extrinsic 用 |
| 许可证 | HF `cardData.license` | `cc-by-4.0` | 可商用,需署名 |

---

## 6. 转换产物(真实生成,已核验)

命令:
```
python3.11 tartanground2mvsnet.py \
  --image_dir raw_download/unzipped/image/image_lcam_front \
  --depth_dir raw_download/unzipped/depth/depth_lcam_front \
  --pose_file raw_download/unzipped/metadata/pose_lcam_front.txt \
  --out_root converted --scan_name tartanground_office_p0000_lcamfront \
  --stride 4 --max_frames 170 --num_src 10 --score_sample_pixels 2500
```
用时 4分46秒(纯 CPU,numpy/cv2,170 帧、全量 O(n²)=28,900 对几何一致性反投影)。

输出(`converted/tartanground_office_p0000_lcamfront/`):
- `blended_images/{:08d}.jpg` × 170
- `cams/{:08d}_cam.txt` × 170(extrinsic 4×4 / intrinsic 3×3 /
  `depth_min depth_interval depth_num depth_max`)
- `cams/pair.txt`(169/170 个 ref 视角有 ≥1 个 src,共视分数矩阵非零条目
  9724/28900,**平均每个 ref 有 57.2 个可用 src**,数量远超训练所需的 8 个)
- `rendered_depth_maps/{:08d}.pfm` × 170(byte-identical 复用官方
  `datasets/data_io.py::save_pfm`)
- `converted/lists/train.txt`(listfile,单行 scan 名)

---

## 7. 烟测结果(真实跑通,非模拟)

### 7.1 官方训练 dataloader `datasets/blend.py::MVSDataset`(`--dataset=blend`)

```
dataset test metas: 169
[getitem] imgs: 9 views, each shape=(3, 640, 640) dtype=float32
[getitem] proj_matrices[stage1..4] shape=(9, 2, 4, 4)
[getitem] depth[stage1] shape=(80,80)   range=[0.556, 26.375] valid_ratio=0.981
[getitem] depth[stage4] shape=(640,640) range=[0.555, 26.641] valid_ratio=0.980
[getitem] depth_values shape=(384,) range=[0.065041, 1.713817]  (视差空间线性采样)
反推 depth_min=0.583 depth_max=15.375  ⇔ 与该 ref 帧 cam.txt 深度行一致
```
`nviews=9` 对齐 `scripts/train/train_casdiffmvs.sh` 里 BlendedMVS 段的
`--trainviews=9`;`ndepths=384` 对齐 `--numdepth=384`。169/170(99.4%)的
ref 帧成功凑够 ≥8 个 src(轨迹边界的 1 帧因共视不足被 `blend.py` 自身逻辑
跳过——这是官方 dataloader 自带行为,不是转换器缺陷)。

### 7.2 `casdiffmvs_mvgZeroDTU.ckpt` 真实前向推理

模型构造超参取自仓库自带 `scripts/test/test_tank_casdiffmvs.sh`(⚠️
这个具体 checkpoint 没有专属测试脚本,借用同系列 BlendedMVS 测试 recipe 是
本次烟测唯一的假设性选择,报告中明确标注,不冒充官方专为它写定)。

checkpoint 读前先查 dataless 标志:`ls -lO` 确认
`.../casdiffmvs_mvgZeroDTU.ckpt` 不带 `dataless` 标记,可安全读取(实际
`ls -lO` 输出该文件大小列显示 `-`,即已是本地实体文件)。

```
[model] missing keys: 0, unexpected keys: 0     # 权重与模型结构完全对齐
[forward] 完成, 用时 5.0s (CPU, batch=1, 9 views, 640x640)
stage_out[0] (1,80,80)   finite_ratio=1.0000 range=[1.086, 15.242]
stage_out[5] (1,640,640) finite_ratio=1.0000 range=[0.858, 15.375]
photometric_confidence[2] (1,640,640) range=[0.0000, 0.9923]
[verdict] 端到端无形状/单位爆炸 = True
```

6 个 stage 输出**全部 100% finite**,最终深度范围 `[0.858, 15.375]` 与
该 ref 帧 `cam.txt` 里的 `depth_min=0.582, depth_max=15.375` 几乎精确重合
(depth_max 完全相等,因为模型的 disparity 采样上界就是从 cam.txt 反推出来的)。
**0 missing/0 unexpected 权重键**说明我们的模型构造超参(view 数、深度层数、
网络维度)与 checkpoint 训练时的结构完全一致,不是凑巧跑通、而是结构对齐。

---

## 8. 实训方案草案(只写方案,不执行,不编时长)

### 8.0 关键前提(需在租机上二次确认)

- "1.44M samples"按 P0000 实测(`num_poses:678` 与该轨迹的 678 帧完全对应)
  推断为**按帧计数、不因 12 路相机相乘**,即同一时间步 12 路相机算一次采样
  机会而非 12 个独立 sample。这是从单个样例推断的,不是官方文档明确定义,
  ⚠️ 建议租机后用另外 1-2 个环境的 `*_metadata.json` 交叉验证再定案。
- 训练用的 ref-view meta 数 ≈ 帧数(本次实测损耗 <1%,轨迹边界效应)。

### 8.1 三个采样/epoch 策略选项

| 策略 | 描述 | ref-view 规模估算 | steps/epoch(batch=4) |
|---|---|---|---|
| **A. 单前视相机全量** | 878 条轨迹全部只用 `lcam_front`,不裁剪 | ≈1.44M(论文口径样本数,按 8.0 前提) | ≈**360,000** |
| **B. 12 路相机全量** | 每条轨迹 12 路相机各自建一个 "scan"(与我们的转换器同一套代码,只是相机名参数化) | ≈1.44M × 12 ≈ 17.3M(与论文"17.3 million RGB images"原文数字吻合,可交叉验证) | ≈**4,320,000**(单 epoch 过大,不现实,列出仅作规模参照) |
| **C. 分层子采样(推荐起点)** | 按环境类别(优先 Indoor/Urban,贴近实际部署场景)+ 单相机 + 固定 stride 抽帧,目标规模控制在 MVG(11.4万)的 3–5 倍 | 目标 34–57 万(人为设定,非官方数字) | ≈**85,000–142,000** |

对照基线:BlendedMVG 现有训练规模 11.4 万 ref-views,batch=4 时
`114,000/4 = 28,500 steps/epoch`。策略 A 单 epoch 步数是 MVG 的 **≈12.6倍**,
策略 C 是 **≈3–5倍**(可控的渐进式扩容起点,不是一步到全量 A/B)。

### 8.2 单步耗时与实际 epoch 时长

**不编。** 本次仅在 CPU 上跑了 1 次 batch=1 的前向(5.0s,不代表训练步——
训练还要反传、优化器、更大 batch、GPU),不能据此外推 epoch 时长。
待租机后用真实 GPU + `--batch_size=4` 跑若干 iteration 实测单步耗时,再乘
上表的 steps/epoch 折算——这一步本次任务范围内没有做,如实标注为待办。

---

## 9. 本次任务的已知局限 / 如实报告的失败与假设

1. 只验证了 1 个环境(Office,室内)、1 条轨迹(P0000)、1 路相机
   (lcam_front)。63 个环境里其余环境的 pose 数值范围、深度分布(尤其室外
   场景是否有"天空 10000m"之类的极值)**没有验证**,转换器里对深度做了
   `<1000` 的过滤兜底,但没有真实数据验证这个阈值对室外环境是否合适。
2. 共视分数的"深度反投影替代 COLMAP 稀疏点"这一适配,是本次任务按官方公式
   做的**推导性延伸**,不是官方发布过的现成脚本,请求方 / 用户复核这一步的
   合理性(第 3.2 节已如实标注,不冒充官方原装)。
3. 烟测用的模型超参数(`test_tank_casdiffmvs.sh` 的结构参数)是"最接近的
   已知官方 recipe",不是这个具体 checkpoint 的专属配方——虽然
   `missing/unexpected keys` 均为 0 证明结构确实对齐,但 `sampling_timesteps`
   /`ddim_eta` 等纯推理期超参未必是训练该 ckpt 时的原装配方,只影响输出质量
   不影响"能不能跑通"的判定。
4. 训练规模测算(第 8 节)依赖"1.44M samples 是否已经是单相机口径"这一从
   单个样例反推的假设,**没有**用第二个环境交叉验证,已在 8.0 节标注为
   待办。
5. 未做:真实 GPU 单步耗时测量、多环境批量转换、室外/大尺度环境的深度范围
   与 sky 值处理验证。这些都需要租机环境才能低成本完成,本机只做了
   可行性证明。
