# OKVIS2 单目-惯性回放 vs ARKit(run-6e2d4b99,640×480,td=+8 ms)

**一句话结论:能跑,单目-惯性稳定初始化;但在同一份输入、同一把 ARKit 尺子、同一 td 下,
OKVIS2 的「因果输出」比现役 RD-VIO/XRSLAM 差约 2 倍(4.70–5.53 cm vs 2.36 cm)。
只有拿它的「跑完之后重算的整条轨迹」(非因果)才追平到 2.57–2.69 cm。
VI-SLAM 的地图/回环在这段 28 秒手持录制上只触发 1–2 次回环,收益有限。**

---

## 0. 运行环境与血统

| 项 | 值 |
|---|---|
| OKVIS2 | `github.com/smartroboticslab/okvis2` @ `a2ea00688cd10988aae7bd52ab7935ce9a657ec0` (2025-12-11),BSD-3 |
| 子模块 | DBoW2 `3924753`,brisk `1ef8b42`,ceres-solver `8533139`(2.2.0),opengv `91f4b19` |
| 本机 | macOS 26.1 (Darwin 25.1.0),arm64 |
| 编译 | `cmake -GNinja -DCMAKE_BUILD_TYPE=Release -DUSE_NN=OFF -DBRISK_BUILD_DEMO=OFF -DHAVE_LIBREALSENSE=OFF` |
| 程序 | 上游自带 `okvis_app_synchronous`(EuRoC/ASL 目录读取器),**未改一行源码** |
| 输入 | `~/Developer/viobench-recordings/_euroc_6e2d4b99_640/`(已存在的 640×480 3× 块平均降采样),1702 帧 / 2842 条 IMU |
| 参照 | `run-6e2d4b99.../arkit_poses.tum`(1702 行,60 Hz,y-up) |
| 评分 | `/usr/bin/python3 ~/Developer/viobench-recordings/ate.py <est.tum> <arkit.tum> --ref-y-up` |

### 依赖上的三个坑(都不是 OKVIS2 的问题,记下来免得下次再踩)

1. **brew 的 `opencv` 是 5.0.0,OKVIS2 只支持 2.4–4。** OpenCV 5 把 `features2d` 改名
   `features`、`calib3d` 改名 `calib`,`external/brisk/agast/CMakeLists.txt:3` 的
   `find_package(OpenCV REQUIRED ... features2d)` 直接 configure 失败。
   🔴 **`/opt/homebrew/opt/opencv@4` 是一条指向 `Cellar/opencv/5.0.0_5` 的陈旧软链**
   (和 `opencv@5` 指向同一个目录)—— 看路径名会被骗,必须看 Cellar 真身。
2. **`brew install opencv@4` 不可行(磁盘)**:它会连带拉 vtk→qtbase/qtdeclarative/qtsvg/proj,
   本机 `~/Developer` 只剩 5.0 GiB,装到一半掉到 2.8 GiB 还在下 —— **已中止**。
   改为用机器上已有的源码树 `~/Developer/opencv-4130-pyoff/opencv-4.13.0` 自建最小 OpenCV 4:
   `BUILD_LIST=core,imgproc,imgcodecs,highgui,features2d,flann,calib3d,video,videoio`,
   装到 `~/Developer/opencv413-okvis-install`。
3. **KleidiCV HAL 会让程序在 97% 处崩**:第一次跑到 `Progress: 97%` 抛
   `OpenCV(4.13.0) arithm.simd.hpp:551: (-3:Internal error) HAL implementation and8u ==> cv_hal_and8u returned -1`。
   这是 OpenCV 4.13 在 arm64 上默认启用的 KleidiCV HAL 与 `cv::bitwise_and` 的交互缺陷,
   与 OKVIS2 无关。用 `-DWITH_KLEIDICV=OFF` 重编 OpenCV 后消失。
   (另外两处小配置:`glog` 必须走 config 模式才能拿到 `glog::glog` 目标,否则 ceres 报
   `<glog/logging.h> was not included correctly`;`Eigen` 必须指到 `eigen@3`=3.4.1,
   brew 的 `eigen` 是 5.0.1,opengv 的 `FindEigen.cmake` 解析不出版本号。)

---

## 1. 能不能单目?**能。**

* `okvis_frontend/src/Frontend.cpp:737` 有显式的 `numCameras()==1` 分支;
  `cameras:` 只写一个 + `sync_cameras: [0]` 就是单目-惯性。
* 本录制上 **0.3 秒内就 `Frontend.cpp:776 Initialized!`**(2D-2D RANSAC),
  健康的那些轮次全程 `TRACKING FAILURE` 计数 = 0。
* 作者论文说单目 VI-SLAM 是 future work —— 这句话在我们的数据上体现为
  **尺度不稳 + 轮次间方差大**,而不是「起不来」。

### 对照实验:EuRoC V1_01_easy(排除「是不是我配错了」)

同一个二进制、上游自带 `config/euroc.yaml`(`do_loop_closures: true`),真值用数据集自带
`state_groundtruth_estimate0`,估计取 body(T_WS)不做 T_SC 换算:

| 臂 | 配对 | Sim3 ATE | 尺度偏差 | SE3 ATE | 用时 |
|---|---|---|---|---|---|
| **双目**-惯性(原配置逐字) | 2872 | 3.64 cm | 0.65 % | **3.84 cm** | 99.4 s |
| **单目**-惯性(只删掉第二个相机块,`sync_cameras:[0]`) | 2872 | 7.77 cm | 0.89 % | **7.94 cm** | 54.1 s |

⇒ 双目 3.84 cm 与 OKVIS2 论文在 V1_01 上的量级一致 ⇒ **我的构建是对的**;
⇒ 单目在 EuRoC 上 **尺度偏差只有 0.89%**,即「OKVIS2 单目本身能守住米制尺度」。
所以我们数据上 3%–31% 的尺度偏差 **不是 OKVIS2 单目的固有上限**,而是这份输入/标定条件下的表现。

---

## 2. 配置文件全文

所有臂共用下面这份,只改 `do_loop_closures` 与 `imu_parameters` 里的四个 sigma。
结构逐段抄自 `okvis2/config/euroc.yaml`,只换设备相关数值。

```yaml
%YAML:1.0
# OKVIS2 config for pocketworld run-6e2d4b99 @ 640x480 (3x block-average of 1920x1440).
# Structure copied verbatim from okvis2/config/euroc.yaml; only the device-specific
# numbers were replaced.  Single camera -> monocular-inertial.
cameras:
     # T_SC = camera -> IMU(sensor).  Taken from XRSLAM q_bc/p_bc (iPhone 14 Pro,
     # upstream author calibration), q_bi = identity / p_bi = 0 so body == IMU.
     # q_bc = [-0.7071068, 0.7071068, 0, 0] (x y z w) -> R = [[0,-1,0],[-1,0,0],[0,0,-1]]
     - {T_SC:
        [ 0.0, -1.0,  0.0,  0.03290364,
         -1.0,  0.0,  0.0, -0.00696553,
          0.0,  0.0, -1.0, -0.00286231,
          0.0,  0.0,  0.0,  1.0],
        image_dimension: [640, 480],
        distortion_coefficients: [0.0, 0.0, 0.0, 0.0],
        distortion_type: radialtangential,
        focal_length: [449.26477050781250, 449.26477050781250],
        principal_point: [318.82309977213544, 239.32139078776044],
        camera_type: gray,
        slam_use: okvis}

camera_parameters:
    timestamp_tolerance: 0.005
    sync_cameras: [0]
    # td = +8 ms on the camera clock (measured optimum on this recording).
    # OKVIS applies timestamp_corrected = timestamp - image_delay, so -0.008 => +8 ms.
    image_delay: -0.008
    online_calibration:
        do_extrinsics: false
        do_extrinsics_final_ba: false
        sigma_r: 0.01
        sigma_alpha: 0.1
        sigma_r_final_ba: 0.03
        sigma_alpha_final_ba: 0.3

imu_parameters:
    use: true
    a_max: 176.0
    g_max: 7.8
    # ---- 臂 A(下面正文解释三个臂的来源)----
    sigma_g_c: 1.696800e-04
    sigma_a_c: 2.000000e-03
    sigma_bg: 0.01
    sigma_ba: 0.1
    sigma_gw_c: 1.939300e-05
    sigma_aw_c: 3.000000e-03
    g: 9.80665
    g0: [ 0.0, 0.0, 0.0 ]
    a0: [ 0.0, 0.0, 0.0 ]
    T_BS:
        [1.0000, 0.0000, 0.0000, 0.0000,
         0.0000, 1.0000, 0.0000, 0.0000,
         0.0000, 0.0000, 1.0000, 0.0000,
         0.0000, 0.0000, 0.0000, 1.0000]

# verbatim from okvis2/config/euroc.yaml
frontend_parameters:
    detection_threshold: 38.0
    absolute_threshold: 150.0
    matching_threshold: 60.0
    octaves: 0
    max_num_keypoints: 700
    keyframe_overlap: 0.60
    use_cnn: false
    parallelise_detection: true
    num_matching_threads: 4

estimator_parameters:
    num_keyframes: 5
    num_loop_closure_frames: 3
    num_imu_frames: 3
    do_loop_closures: false        # VIO 臂 false / SLAM 臂 true
    do_final_ba: false
    enforce_realtime: false
    realtime_min_iterations: 3
    realtime_max_iterations: 10
    realtime_time_limit: 0.035
    realtime_num_threads: 3
    full_graph_iterations: 15
    full_graph_num_threads: 3
    p_dbow: 0.4
    drift_percentage_heuristic: 1.35

output_parameters:
    display_matches: false
    display_overhead: false
```

### 数值来源逐条说明(哪些是查来的,哪些是我换算的)

* **`T_SC`**:OKVIS 的 `T_SC` 就是 camera→sensor(IMU)。XRSLAM 的
  `q_bc=[-0.7071068,0.7071068,0,0]`(xyzw)展开为 `R=[[0,-1,0],[-1,0,0],[0,0,-1]]`
  (det=+1,校验过),`p_bc=[0.03290364,-0.00696553,-0.00286231]`。
  与 `_sweep/device_bench.yaml` 里 `cam0.T_BS` 的 16 个数逐位相同 —— 直接抄。
  因 `q_bi=identity/p_bi=0`,body==IMU,所以 `T_SC = T_BC`。
* **内参(640 档)**:1920 档 `fx=fy=1347.7943115234375, cx=957.4692993164062, cy=718.9641723632812`;
  转换器 `pwvi_to_euroc.py` 的降采样是 **严格 3×3 块平均**
  (`reshape(H//3,3,W//3,3).mean(axis=(1,3))`)。按 OpenCV 的像素中心约定,
  `fx' = fx/3`,`c' = (c+0.5)/3 - 0.5` ⇒ `fx=fy=449.2648, cx=318.8231, cy=239.3214`。
  (若改用「朴素 c/3」= 318.8231→319.1564,差 1/3 像素,量级上可忽略;这里选 OpenCV 约定。)
* **畸变**:录制无畸变 ⇒ `radialtangential` + 四个 0(OKVIS 的 radtan 就吃 4 个系数)。
* **`image_delay: -0.008`**:OKVIS 的语义是
  `timestamp_camera_correct = timestamp_camera - image_delay`(`Parameters.hpp:81`,
  施加点 `ThreadedSlam.cpp:146`),所以要做「相机时间戳整体 +8 ms」就填 **-0.008**。
  ✅ **运行期自证**:输出轨迹第一行时间戳 `5073352289208`,
  对应输入 `cam0/data.csv` 第 7 帧 `5073344289208`,差 **恰好 8,000,000 ns**。
  (另:+8 ms < 60 Hz 帧间隔的一半 8.334 ms,所以 `ate.py` 的最近邻配对仍然配到同一张图,
  1695/1695 全配上,不存在错位。)
* **IMU sigma —— 这是本次最大的不确定项,所以做了三个臂,每个臂的数都有出处,我没有自己调参:**

| 臂 | sigma_g_c | sigma_a_c | sigma_gw_c | sigma_aw_c | 出处 |
|---|---|---|---|---|---|
| **A** | 1.6968e-4 | 2.0e-3 | 1.9393e-5 | 3.0e-3 | 本机 `device_bench.yaml` 的 `noise.cov_*` **开方** |
| **B** | 8e-4 | 1e-2 | 2.2e-4 | 1e-3 | `okvis2/config/tumvi_slam_512.yaml` 逐字(作者自己写的**手持**设备档) |
| **C** | 20e-4 | 20e-3 | 20e-5 | 20e-3 | `okvis2/config/euroc.yaml` 逐字(作者自己的 EuRoC 档) |

  臂 A 的换算依据 —— ✅ **已在 XRSLAM 源码与上游文档里逐条核实,不是推断**
  (源码树在 `~/Developer/xrslam`,不在 `pocketworld/vendor/xrslam`,后者只有预编库和 transport):

  * 上游文档 `~/Developer/xrslam/docs/en/config_parse.md:26-29` 原文写明单位:
    `cov_g` = **(rad/s/sqrt(hz))^2**、`cov_a` = **((m/s^2/sqrt(hz))^2)**、
    `cov_bg` = **((rad/s^2/sqrt(hz))^2)**、`cov_ba` = **((m/s^3/sqrt(hz))^2)**。
  * 读取:`xrslam-extra/src/xrslam/extra/yaml_config.cpp:222-236` 把四项原样存进
    `m_*_noise_cov`;喂给引擎在 `xrslam/src/xrslam/core/detail.cpp:183-184`。
  * 消费:`xrslam/src/xrslam/estimation/preintegrator.cpp:66-78` 用的是
    `white_noise_cov = cov_w * (1/dt)` / `cov_a * (1/dt)`,以及
    `delta.cov(ES_BG,ES_BG) += cov_bg * dt`、`(ES_BA,ES_BA) += cov_ba * dt`
    —— 正是「连续时间密度的**协方差**」离散化的教科书写法(σ_c²/dt 与 σ_w²·dt)。

  ⇒ `cov_*` 确为 σ² 且单位与 OKVIS 的 `sigma_g_c [rad/s/sqrt(Hz)]` /
  `sigma_a_c [m/s^2/sqrt(Hz)]` / `sigma_gw_c [rad/s^2/sqrt(Hz)]` /
  `sigma_aw_c [m/s^3/sqrt(Hz)]` **逐项对得上**,开方即得。
  (OKVIS `euroc.yaml` 把 `sigma_aw_c` 的注释写成 `[m/s^2/sqrt(Hz)]`,量纲上应为 m/s^3,
   是上游注释笔误,不影响数值。)
  数值校验:开方得 `1.70e-4 / 2.0e-3 / 1.94e-5 / 3.0e-3`,与 EuRoC 数据手册
  (1.2e-4 / 2.0e-3 / 4e-6 / 3e-3)同量级;不开方则差 4 个数量级。
* **`g: 9.80665`**:与 XRSLAM 引擎写死的值一致(记忆里北京实际 9.80148,差 0.053%),
  为了「同一把尺子」没有改成当地值。
* **`a0`/`g0` 置零**:上游 euroc.yaml 填的是 EuRoC 那台 IMU 的实测偏置,我们没有对应实测值。

---

## 3. 命令

```bash
# 依赖(最小 OpenCV 4)
cd ~/Developer/opencv413-okvis-build
cmake -GNinja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=$HOME/Developer/opencv413-okvis-install \
  -DBUILD_LIST=core,imgproc,imgcodecs,highgui,features2d,flann,calib3d,video,videoio \
  -DWITH_KLEIDICV=OFF -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF \
  -DBUILD_opencv_python3=OFF -DWITH_FFMPEG=OFF -DWITH_AVFOUNDATION=OFF -DWITH_PROTOBUF=OFF \
  ~/Developer/opencv-4130-pyoff/opencv-4.13.0 && ninja && ninja install

# OKVIS2
git clone --recurse-submodules https://github.com/smartroboticslab/okvis2.git ~/Developer/okvis2
cd ~/Developer/okvis2 && mkdir build && cd build
cmake -GNinja -DCMAKE_BUILD_TYPE=Release -DUSE_NN=OFF -DBRISK_BUILD_DEMO=OFF -DHAVE_LIBREALSENSE=OFF \
  -DOpenCV_DIR=$HOME/Developer/opencv413-okvis-install/lib/cmake/opencv4 \
  -DEIGEN_INCLUDE_DIR=/opt/homebrew/opt/eigen@3/include/eigen3 \
  -DEigen3_DIR=/opt/homebrew/opt/eigen@3/share/eigen3/cmake \
  -Dglog_DIR=/opt/homebrew/lib/cmake/glog \
  -DCMAKE_CXX_FLAGS="-DGLOG_USE_GLOG_EXPORT" \
  -DCMAKE_PREFIX_PATH="/opt/homebrew/opt/eigen@3;/opt/homebrew" ..
ninja
cp ~/Developer/okvis2/resources/small_voc.yml.gz .   # 程序按 argv[0] 同目录找词典

# 数据集目录(图片用软链,避免再占 328 MB)
d=<SCRATCH>/dsC_slam1; mkdir -p $d/cam0 $d/imu0
ln -sfn ~/Developer/viobench-recordings/_euroc_6e2d4b99_640/cam0/data $d/cam0/data
cp ~/Developer/viobench-recordings/_euroc_6e2d4b99_640/cam0/data.csv $d/cam0/
cp ~/Developer/viobench-recordings/_euroc_6e2d4b99_640/imu0/data.csv $d/imu0/

# 回放(上游自带 app,两个参数就是 yaml + mav0 同构目录)
~/Developer/okvis2/build/okvis_app_synchronous <SCRATCH>/pw640_slam_eurocsig.yaml $d

# 出的两个文件:
#   $d/okvis2-slam_trajectory.csv        <- 因果/逐帧流式输出(回调即写)
#   $d/okvis2-slam-final_trajectory.csv  <- 跑完后从最终 realtimeGraph_ 重建整条轨迹(非因果)

# T_WS(body) -> T_WC(camera),再打分
python3 <SCRATCH>/okvis_csv_to_tum.py $d/okvis2-slam_trajectory.csv out_body.tum out_cam.tum
/usr/bin/python3 ~/Developer/viobench-recordings/ate.py out_cam.tum \
  ~/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum --ref-y-up
```

`okvis_csv_to_tum.py` 做的事:读 OKVIS csv 的 `timestamp[ns], p_WS_W, q_WS(xyzw)`,
`T_WC = T_WS · T_SC`(即 `p_WC = p_WS + R_WS·p_SC`,`R_WC = R_WS·R_SC`),
用的是喂给 OKVIS 的同一个 `T_SC`。**下面表里的 ATE 一律是相机位姿口径**(与 ARKit 同口径);
body 口径只差那条 33.75 mm 杠杆臂,实测两者差 0.05–0.2 cm(见 §4.4)。

---

## 4. ATE 结果

参照基准(同录制/同尺子/同 td,来自任务书):
**XRSLAM@640×480 SE3 2.36 cm / 尺度偏差 4.27%**;@1920×1440 SE3 1.99 cm / 尺度 0.22%。
我只跑了 **640 档**(1920 档未做,原因见 §5),所以只与 640 档比。

### 4.1 因果输出(`okvis2-*_trajectory.csv`,逐帧回调即写 —— 与 XRSLAM 的 `--csv` 同性质)

| 臂 | 模式 | 轮次 | Sim3 ATE | 尺度偏差 | **SE3 ATE** | 跟踪失败帧 |
|---|---|---|---|---|---|---|
| A(设备 σ) | VIO | 1 | 10.88 | 31.17 % | 18.62 | 0 |
| A | VIO | 2 | 33.57 | 100 % | **488 749** ⚠发散 | 71 |
| A | VIO | 3 | 3.56 | 10.76 % | 5.51 | 0 |
| A | VIO | 4 | 26.70 | 100 % | **1 055 827** ⚠发散 | 752 |
| A | VIO | 5 | 4.80 | 18.74 % | 9.34 | 0 |
| A | SLAM | 1 | 4.79 | 15.73 % | 8.07 | 0 |
| A | SLAM | 2 | 25.21 | 100 % | **10 522 559** ⚠发散 | 1293 |
| B(TUM-VI σ) | VIO | 1/2/3 | 4.46 / 5.48 / 6.06 | 8.04 / 7.63 / 12.23 % | 5.40 / 6.18 / 7.74 | 0 |
| B | SLAM | 1/2/3 | 5.28 / 4.35 / 3.18 | 4.62 / 7.22 / 13.65 % | 5.54 / 5.12 / 6.37 | 0 |
| C(EuRoC σ) | VIO | 1/2/3 | 3.67 / 4.80 / 5.94 | 3.82 / 2.94 / 6.57 % | 3.92 / 4.91 / 6.42 | 0 |
| **C** | **SLAM** | 1/2/3 | 5.48 / 4.71 / 4.19 | **2.04 / 4.58 / 5.76 %** | **5.53 / 5.00 / 4.70** | 0/2/0 |
| D(B 的 σ,全部线程数=1) | VIO | 1/2 | 5.14 / 5.54 | 9.15 / 6.19 % | 6.22 / 6.00 | 0 |
| — | — | — | — | — | — | — |
| **XRSLAM/RD-VIO 基准** | VIO | — | 2.36* | **4.27 %** | **2.36** | — |

(单位 cm;*基准行只给了 SE3 2.36 与尺度 4.27%。)

### 4.2 非因果输出(`okvis2-*-final_trajectory.csv`,跑完后整条重建)

| 臂 | 模式 | 轮次 | Sim3 ATE | 尺度偏差 | **SE3 ATE** |
|---|---|---|---|---|---|
| A | VIO | 1/3/5(健康轮) | 4.83 / 2.76 / 2.61 | 13.97 / 12.41 / 14.86 % | 7.43 / 5.67 / 6.64 |
| A | SLAM | 1 | 3.55 | 16.00 % | 7.54 |
| B | VIO | 1/2/3 | 2.17 / 2.65 / 3.54 | 4.96 / 5.26 / 15.10 % | 2.84 / 3.28 / 7.15 |
| B | SLAM | 1/2/3 | 2.45 / 2.01 / 2.34 | 5.37 / 9.03 / 12.76 % | 3.15 / 4.02 / 5.63 |
| C | VIO | 1/2/3 | 2.09 / 2.22 / 2.38 | 7.53 / 5.40 / 6.98 % | 3.53 / 2.99 / 3.54 |
| **C** | **SLAM** | 1/2/3 | **2.66 / 2.17 / 1.89** | **1.00 / 4.07 / 4.71 %** | **2.69 / 2.63 / 2.57** |
| D | VIO | 1/2 | 2.79 / 2.58 | 8.02 / 6.23 % | 4.14 / 3.47 |

### 4.3 运行时长 / 每帧耗时

| 项 | 值 |
|---|---|
| 单场输入 | 1702 帧,28.37 s,60 Hz;输出 **1695** 帧位姿(IMU 起始比相机晚 77 ms,开头 6 帧被 `ThreadedSlam.cpp:294` 丢弃,另 1 帧用于初始化) |
| `total processing time`(程序自报) | **27.0–27.8 s**(健康轮,A/B/C/D 各臂无显著差别) |
| 每帧 | **≈16.3–16.5 ms**(相机 60 Hz 的预算是 16.67 ms ⇒ 在这台 Mac 上刚好实时) |
| 大头(臂 C SLAM run1,1678 帧) | `3 Optimise` 9.29 ms/帧(56%)、`2 Match` 1.97 ms、`7 Marginalise` 1.11 ms、`1 DetectAndDescribe` 1.37 ms、`4 Prepare publishing` 0.59 ms |
| 回环 | `2.03 loop closure query` 0.074 ms/帧;**整场只 add 了 1–2 次回环** |
| ⚠发散轮 | 43 s / 191 s / 229 s(跟踪一崩,优化器迭代数暴涨) |
| EuRoC 对照 | 双目 99.4 s / 2911 帧 = 34.1 ms/帧;单目 54.1 s = 18.6 ms/帧(752×480,20 Hz) |

### 4.4 body vs camera 口径

臂 A VIO run1:body SE3 18.48 / cam SE3 18.62;臂 A SLAM run1:body 8.10 / cam 8.07;
final:body 7.56 / cam 7.54。**两种口径差 0.03–0.15 cm**,不改变任何结论。
表里全部是 **camera 口径**(乘过 `T_SC`)。

---

## 5. 与基准的对比 / 回答那个问题

> 「VI-SLAM 档(有地图/回环)在同一份输入上能不能比现役 RD-VIO/XRSLAM 更好?」

**同口径(因果、逐帧)下:不能,差约 2 倍。**
最好的那个臂(C,SLAM)三轮 SE3 = **5.53 / 5.00 / 4.70 cm**,中位 5.00 cm,
对 XRSLAM 的 2.36 cm 是 **2.1×**。尺度偏差 2.04 / 4.58 / 5.76 %,中位 4.58% ≈ 基准的 4.27%,
**不优也不显著劣**。

**换非因果口径才追平:** 臂 C SLAM 的 `final_trajectory` SE3 = **2.69 / 2.63 / 2.57 cm**,
中位 2.63 cm,与 2.36 cm 只差 11%,尺度偏差中位 4.07% 略好于 4.27%。
🔴 **但这不是公平对比** —— `final_trajectory.csv` 是跑完整场之后从最终位姿图重建的整条轨迹,
后面的观测会回头修正前面的位姿;XRSLAM 的逐帧输出没有这个。要拿它当结论,必须同时说明
「AR 实时渲染吃不到这条轨迹」。

**回环本身的贡献很小但为正**:臂 C,VIO final 中位 3.53 cm → SLAM final 中位 2.63 cm(好 25%);
因果口径 VIO 4.91 → SLAM 5.00,**没有差别**。这段 28 秒手持录制整场只检出 **1–2 次回环**,
地图/回环这条路在这种时长的素材上本来就没什么可吃的。

**三个 σ 臂的排序揭示了真正的瓶颈是尺度不是姿态:**
所有健康轮的 **Sim3 ATE 都在 1.9–6.1 cm**,而 SE3 与 Sim3 的差值(=尺度造成的部分)
从臂 A 的 7.7 cm 一路收到臂 C 的 0.03 cm。换句话说 **OKVIS2 单目在这份数据上「形状」一直没问题,
坏的是米制尺度**,和我们在 XRSLAM 上查了一周的结论(4.13% 尺度偏差是瓶颈)是同一个病。

🔴 **关于臂 C 要打的折**:三个 σ 臂里 C 最好,**而 C 是我按 ATE 事后挑出来的**。
而且现在 σ 换算已核实 ⇒ **唯一物理正确的是臂 A,它最差且会发散**;C 的 σ 比设备实测值大 **11.8×(陀螺)/ 10×(加速度计)**。
它的 σ 来自作者的 EuRoC 配置(ADIS16448 @200 Hz,且作者已经刻意放大了约 10×),
**不是我们这台 iPhone 的实测值**。所以「2.57 cm」是**三选一之后的最优值,不是样本外成绩**;
诚实的区间应该报 **4.70–6.42 cm(因果)/ 2.57–7.15 cm(非因果)**。
唯一有设备依据的臂 A 反而最差且 **5 轮里 2 轮直接发散到公里级**。

---

## 6. 失败 / 未做项(逐条)

1. 🔴 **1920×1440 档没跑。** 任务书的闸是「`df -h ~/Developer` 剩 ≥4 GB 才重生成」。
   实测开工时 **5.0 GiB**,但 brew 拉依赖 + 自建 OpenCV 之后只剩 **2.0–2.9 GiB**,
   而转换产物 2.5 GB ⇒ 不满足闸,**只做了 640 档**,因此只与 640 基准(2.36 cm / 4.27%)比。
2. 🔴 **OKVIS2 单目在这份数据上不确定:同二进制同输入,5 轮臂 A 里 2 轮发散到 4.9 km / 10.6 km。**
   发散轮的特征是 `TRACKING FAILURE: quality=0` 刷屏(71 / 752 / 1293 帧)+ 用时从 27 s 涨到 43–229 s。
   臂 B/C/D 共 13 轮没有一次发散。
3. 🔴 **逐位不可复现,且把线程数全调到 1 也没解决**(臂 D:`parallelise_detection:false`,
   `num_matching_threads/realtime_num_threads/full_graph_num_threads` 全 = 1,
   两轮输出仍 `DIFFER`)⇒ 不确定性不止来自可配置的线程数。
   所以表里所有数字都必须按「多轮区间」读,不能引用单轮。
4. **`do_final_ba` 全程关着**(与 `config/euroc.yaml` 一致)。理由:`okvis_app_synchronous.cpp:170-180`
   在 do_final_ba 分支里调 `cv::imshow`/`imwrite`,需要 GUI;且开了就不是「同口径」了。
   ⇒ **没有测 full BA 档**,这是一个未探明的上限。
5. **没有做 td 扫描。** 按任务书直接用 +8 ms。OKVIS2 有 `image_delay` 也有
   `online_calibration.do_extrinsics`(在线标外参)—— 后者没开,也没测。
6. **没有测卷帘补偿**(OKVIS2 无此项)、没有测曝光中点换算(这份录制没有 `exposure_s`)。
7. ~~`cov_* → σ` 的开方换算是推断~~ ✅ **已核实**(上游文档单位 + `preintegrator.cpp:66-78`
   的 `cov_w/dt`、`cov_bg*dt` 用法,见 §2 末)。⇒ **臂 A 用的就是这台 iPhone 的正确噪声模型**,
   这让臂 A 的结果变成一个更强的负面结论:**喂物理正确的 σ 时,OKVIS2 单目在这份数据上
   5 轮里 2 轮发散**;要它稳,必须像作者自己的 euroc/tumvi 配置那样把 σ 放大 5–12 倍。
   (🔴 顺带修正我最初的判断:我一度以为本机没有 XRSLAM 算法源码 —— 有,在
   `~/Developer/xrslam`,我第一次只 grep 了 `pocketworld/vendor/xrslam`。**又一次「先 grep 自己的仓」**。)
8. **未做:** 与 Basalt / 其它 VI-SLAM 的横比;1920 档;更长的录制(回环才有意义);
   多场录制(本次只有这一场,所有方差都是同一场内的轮次方差)。

## 7. 产物位置

* OKVIS2 源码 + build:`~/Developer/okvis2`(build 目录含 `okvis_app_synchronous` 与 `small_voc.yml.gz`)
* 最小 OpenCV 4.13:`~/Developer/opencv413-okvis-install`(build 树 `~/Developer/opencv413-okvis-build`,可删)
* 本次全部 yaml / 日志 / 轨迹 / tum:本报告同目录
  (`pw640_{vio,slam}.yaml`、`pw640_{vio,slam}_tumvi.yaml`、`pw640_{vio,slam}_eurocsig.yaml`、
   `pw640_vio_tumvi_1thread.yaml`、`euroc_mono.yaml`、`run_*.log`、`ds*/okvis2-*.csv`、`*.tum`、
   `okvis_csv_to_tum.py`)
* **没有向 `~/.claude/` 写任何东西;没有开摄像头;没有录制;没有碰 iPhone。**
