# Host-replay 塌陷定罪 — cap_1785934283657550 (201 帧)

日期 2026-08-07。输入:`replay_cap50/session.db`(特征源)+ `poses_cap50.jsonl`。
所有臂同一输入、同一 bench CLI(`k max_frames=0 ratio=0.700`)。

## 结论

**罪魁 = MANDATORY-ARKIT-GRAVITY V1 的 upright 两视几何(`mandatory_gravity_tvg_v1.cc`
/ `upright_relative_pose_v1.cc`,2026-08-04)成为唯一且无条件的 TVG 估计器。**

不是用户列出的任何一个 08-06 嫌疑人。

## 判据链(全部实测)

### 1. 匹配器逐对逐字节相同 — 断层在 TVG,不在匹配
08-05 输出库 vs 现树 K22 臂,**2787 个共同 pair**:

| 量 | 08-05 | 现树 K22 |
|---|---|---|
| 共同 pair 原始 match 数完全相同 | 2787/2787 | 2787/2787 |
| 共同 pair 原始 match 均值 | 336.6 | 336.6 |
| 共同 pair TVG inlier 均值 | **291.4** | **115.4** |
| TVG 存活率 | **86.6%** | **34.3%** |

按现树 config 分组(同一批 raw match):

| k22 config | pairs | raw | 08-05 inliers | k22 inliers | 丢失 |
|---|---|---|---|---|---|
| CALIBRATED | 2152 | 646222 | 562627 (87.1%) | 238306 (**36.9%**) | 324321 |
| PLANAR_OR_PANORAMIC | 635 | 291763 | 249639 (85.6%) | 83278 (28.5%) | 166361 |

⇒ 损失是全面的,不只是被改判成 planar 的那批;CALIBRATED 那 2152 对也从 87.1%
掉到 36.9%。config 直方图:08-05 = {CALIBRATED 3070, PLANAR 2};现树 =
{CALIBRATED 2163, PLANAR 641}(planar 误判率涨 ~350×)。

### 2. 代码定位
全 `official_pipeline/src` 树内 `colmap::EstimateTwoViewGeometry(` **只剩 1 处调用**,
在 `mandatory_gravity_tvg_v1.cc:120`,且带 `force_H_use=true`(只算单应)。
COLMAP 标准本质矩阵 RANSAC 已成死代码;每一条 TVG 都走 upright 3 点解算器。
`mandatory_gravity_tvg_v1.cc` / `upright_relative_pose_v1.cc` **无任何 env 开关**。

源码快照 bisect(`grep -c`):

| 快照 | mtime | mandatoryTVG 调用 | plain colmap TVG 调用 |
|---|---|---|---|
| tailcache_device_candidate_20260803 | 08-03 10:01 | 0 | **10** |
| krewire_install_20260806 | 08-06 13:49 | 11 | 0 |
| loop_p5_install_20260806 | 08-06 15:43 | 11 | 0 |
| loop_top8_install_20260806 | 08-06 16:55 | 11 | 0 |
| gpu_hang_recovery_20260806 | 08-06 22:47 | 11 | 0 |
| 现树 | 08-07 13:25 | 11 | 0 |

### 3. 下游塌陷是 TVG 的因变量
live create/grow/merge 吃的就是 TVG inlier 集。
`track_len` 现树恒为 **2.002**(几乎每个 live 点都是裸 2-view,grow 从不成功);
08-05 为 2.654。live model 133323 → 6479(20×)。

## 排除(实测,非推理)

### K-REWIRE(K20 → 10+2,08-06,用户已签)— **不是**
`OFFICIAL_AETHER_LIVE_CAND_K=22` 精确还原 08-05 pair 拓扑
(cand 12/20/22/22/22,sum_cand 4313 vs 08-05 的 4113,TVG pair 2804 vs 3072),
点数几乎不动:**18205 → 18227**。
K-REWIRE 只解释 TVG **pair 数** 3072→2065,不解释 inlier 塌陷。

### 全部 08-06 改动(空间序复活/描述子驻留/visual-loop p5/scale-persist _v2)— **不是**
`build-host-fullbench/official_replay_bench_exe`(链接时间 **Aug 5 2026 13:18:57**,
早于全部 08-06 改动;仍带 K20 硬编码,实测 sum_cand = **4113**,与 08-05 基线逐字相同)
在默认 env 下同样塌陷:**n_points=17031,live_total=6389,TVG 均值 115.3**。
⇒ 08-06 之后的任何改动都不可能是原因。

## 各臂实测表

| 臂 | 二进制 | env | n_reg | n_points | live_total | sum_cand | TVG 均值 |
|---|---|---|---|---|---|---|---|
| 08-05 基线 | Aug 5 23:12 | ? | 200 | **115270** | 133323 | 4113 | **266.5** |
| ctl_k12 | Aug 7 13:25 | 默认 | 192 | 18205 | 6479 | 2598 | 137.8 |
| k22 | Aug 7 13:25 | LIVE_CAND_K=22 | 188 | 18227 | 6388 | 4313 | 114.9 |
| aug5bin_k12 | **Aug 5 13:18** | 默认 | 189 | 17031 | 6389 | **4113** | 115.3 |
| tri_k12 | Aug 7 13:25 | OFFICIAL_TRIANGULATE=1 | 193 | 23072 | 15971 | 2598 | — |
| tri_k22 | Aug 7 13:25 | +LIVE_CAND_K=22 | 192 | 21667 | 16472 | 4313 | — |
| armE_k22 | Aug 7 13:25 | +TRI_IGNORE_2VIEW=0 | 196 | 25945 | 22511 | 4313 | — |

## 已核销的输入等价性(排除 harness 混淆)

- keypoints:`fed ... n_kp=8192/8168/8192` 三处采样逐帧一致。
- poses:用 08-05 基线**自己**的 `replay_filter_ab/session.db.arkit_pose_v1` 重生成
  poses.jsonl,与 `poses_cap50.jsonl` **SHA-256 完全相同**
  (`00edf0b8aaa2aa18…`)。重力由 pose 内部导出,故也相同。
- 内参:源库 vs 08-05 输出库 cameras 表 201 个、201 组互异参数、逐个数值相同。
- 匹配:见判据 1(2787/2787 逐对相同)。

## 第二个未解释的差异(次要,已量化)

08-05 基线日志:`capture-time official TriangulateImage added **414893** obs`;
现树与 **Aug-5 13:18 二进制** 均为 **0**。该路径由
`OFFICIAL_AETHER_OFFICIAL_TRIANGULATE` 把门,08-03 起每个快照默认都是 OFF。
⇒ 08-05 那次跑要么带了该 env,要么当晚工作树默认不同。
单独补上它只把 18205 抬到 23072(+TRI_IGNORE_2VIEW=0 到 25945),
远不足以解释缺口,故为次要项,不是罪魁。

## 未验证(明确标注为假说,需下一步实测)

upright 3 点解算器把相对旋转约束成绕重力轴的单自由度。若逐帧 ARKit 重力之间
存在哪怕很小的不一致(VIO 漂移,或重力由已漂移的 pose 导出),该模型就拟合不到
真实相对旋转 ⇒ 系统性少 inlier。这与 08-04 复核给出的
"强制 ARKit 重力 = 不可签名(1 blocker + 2 high)" 一致,但**本次未做单变量验证**
(该路径无 env 开关,单变量 A/B 需要改产品源码重编,未获授权,故未做)。

## 复现命令

```bash
cd /Users/kaidongwang/Documents/progecttwo/_artifacts/floater_removal_20260805/bisect_20260807
BIN=/Users/kaidongwang/Developer/Aether3D-cross/aether_cpp/third_party/glomap_vendor/build-host/official_replay_bench_exe
"$BIN" work_src.db poses_cap50.jsonl <out_dir> 12 0 0.700
```

`src_session_RO.db`(chmod 444)= 不可再生源库的保护副本,
sha256 `6a9a550c6df03cad2369a85773f19484993ca32705171505174c44e368a3c6fd`。
`work_src.db` 是给 bench 读写用的工作副本。
