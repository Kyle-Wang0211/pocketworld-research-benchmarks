# #3 — DSO 逆深度区间成熟判据(cap50 原型,diagnostic-only)

铁律遵守:仅写研究 worktree;未碰生产代码;未 reset/clean/动他人 dirty;未 git commit(留编排者统一提交)。
**不自批准**——本目录只出脚本 / 数字 / viewer / manifest + SHA-256,不声称"修好/成功"。
证据标注:🟢=有实测数据支撑;🔴=诚实负面结论 / 未解决取舍。

---

## 任务与机制

用 DSO 式逆深度区间 `[idepth_min, idepth_max]` 收敛,替代生产的固定"三角化视差角 ≥ 2°"出生门,
验证它能否把低视差鬼点扣在 immature。DSO(Engel 2016,ImmaturePoint 极线搜索)机制:每点带逆深度区间,
视差足够→区间收窄→收敛才激活出生;视差不足→区间宽→不激活。区间半宽的一阶模型:

```
w_rel = (sigma_px / f) / sin(alpha_max)          （相对逆深度,∝ 1/视差）
```

出生门:`w_rel <= tau`(mature=出生),否则 immature=扣住。

数据源(SHA-256 见 manifest.json):生产云 `sfm_sparse.ply`(92,849 点,无 per-point track)+ 精化位姿
`sfm_sparse_meta.json` + COLMAP DB `sfm_live.db`(keypoints/verified two_view_geometries)。
生产云不带 track,故从 DB 的**已验证**内点匹配独立重建 track、用精化位姿三角化、量每点视差。
`image_id-1 == frame_id` 映射经三角化重投影 **中位 0.56px** 验证后才使用。

---

## 🟢 主结果(`dso_interval_gate.py`)—— 几何区间门 = 亚 2° 角度门,扣不住任何 2° 门放行的点

重建 track:**89,594**(2-view 57,820 / 3-4 视 23,309 / ≥5 视 8,465),对齐生产 `n_points3d=90,615`,重建保真。

2-view 视差分布(🟢):中位 **5.9°**,p10 1.6°,p5 1.0°;**<2° 仅 12.9%**,<1° 4.9%。
即多数 2-view 点其实视差不低。

关键恒等式:`w_rel <= tau` ⟺ `alpha >= arcsin(sigma_px/(f*tau))`。**几何区间门在数学上就是一个角度门**,
只是把阈值用焦距/尺度归一化表达。4K 成像(f=2558.97px):

| sigma_px | 在 2° 处的 w_rel | tau=0.05 等价角 | tau=0.10 等价角 |
|---|---|---|---|
| 1px(已精化对应) | 1.1% | 0.45° | 0.22° |
| 3px(temporal_detail 3px 容差、永不精化) | 3.4% | **1.34°** | 0.67° |

**所有 6 组 (sigma, tau) 配置下 `dso_only_held = 0`**(全云 / 2-view / chair-ROI / floater 均如此):
DSO 几何区间门的等价角(0.11°–1.34°)永远 **低于** 固定 2° 门,因此它 **无法扣住任何 2° 门已放行的点**,
只会更宽松地多产 sub-2° 点(`dso_only_born`,如 sigma3/tau0.1 全云 6,473 / 2-view 6,182 / chair-ROI 307)。

floater 代理(reproj>2px 或深度不合理,仅几何不稳代理、非标注鬼点):固定 2° 门扣住 **8.6%**(2-view 内 19.9%);
DSO 几何门扣得 **更少**(sigma3/tau0.05:6.0% / 15.2%;sigma3/tau0.1:2.6% / 6.6%)。几何区间门抓 floater 严格更差。

**结论(🔴 对任务假设②的诚实证伪,几何读法):** median-17° 仍错的点(§7.5)视差高→几何区间**窄**→
DSO 几何门只会照样放行,绝不会扣成 immature。任务设想的"几何区间扣住高视差鬼点"**不成立**。
根因:4K + 已验证匹配下,即便 2° 视差逆深度精度已达 ~1%,几何不是这些鬼点的判别量。

viewer:`viewer_gate_topdown_and_roi.png`(左全云 / 右 chair-ROI;蓝=两门都出生,橙=DSO-only 出生,
**红=DSO-only 扣住,计数为 0**,故图上无红点——这就是主结论的肉眼版)。

---

## 🔴 光度区间探针(`photometric_interval_probe.py`)—— 探索性、**未得可信信号**

DSO 真正让点成熟的是**光度**极线搜索区间(ZNCC-vs-逆深度 在 margin 内的宽度 / 多峰性),不是纯几何基线。
本探针对冻结样本(每类 5 点)沿参考射线扫逆深度、投进其余观测视做多视 ZNCC。

**诚实负面:** 该探针用**图像对齐 7×7 窗、无单应 warp**,得到的 ZNCC-vs-逆深度 曲线**逐 bin 剧烈抖动**
(见 `viewer_photometric_profiles.png`,已标注 EXPLORATORY/INCONCLUSIVE),`photo_relwidth` 多落回单 bin 分辨率地板(=0),
高视差控制组因视点变化 ZNCC 峰值反而低(0.42)。**这些数字不足以作为光度区间证据,不据此下任何结论。**
一个可信的光度区间需平面诱导单应 warp patch + 鲁棒聚合(未来工作)。

**但 plane-sweep 鬼点的光度区间已被 §7.5 正经测过(可引用,🟢):** `14_planesweep_height_hypothesis_probe`
沿认证法线做的高度探针显示 **8/10 悬疑样本 floor 假设以 ≥0.164 中位 ZNCC 击败所有抬高假设**——
即压扁鬼点在地板深度处光度**峰值锐利**、光度区间也**窄**。故光度区间**同样会让鬼点成熟、同样扣不住**。

---

## 综合裁决(🔴 收敛于 #5,留用户签决)

- 几何逆深度区间门 = 亚 2° 角度门:对 17° 鬼点**无效**(实测 dso_only_held=0,全配置)。
- plane-sweep 鬼点在其所处深度**光度自洽**(§7.5:floor 胜抬高 8/10):光度单射线区间**也扣不住**。
- 因此**单射线区间机制(几何或光度)都抓不住这些鬼点**——与 #5 结论一致:缺的是 free-space/opposition
  证据(per-view 独立深度图),不是任何区间门。
- 区间机制对 SfM 有一处真实、但方向相反的作用:它按"实际逆深度精度"而非武断角度决定出生,会把
  sub-2° 但 4K 下几何足够精的点判为可出生(`dso_only_born`)。这是**放宽而非收紧**,是否可取需用户签决,本原型不预判。

**给继任者的真候选方向(不在本原型范围):** 若要用区间机制抓压扁鬼点,必须给候选补 per-view 深度/占据
证据(free-space 看穿票 / opposition),让"贴错深度"在某些视里产生反对,再让区间/生命周期消费该反对。
纯视差或纯单射线光度都不够。

---

## 文件

| 文件 | 说明 |
|---|---|
| `dso_interval_gate.py` | 主脚本:重建 track、几何区间门 vs 固定 2° 门、floater/ROI 分析、viewer、manifest |
| `gate_stats.json` | 全 6 组 (sigma,tau) × 各人群 的出生/扣住/分歧集/质量/floater 统计 |
| `tracks.npz` | 89,594 重建 track:xyz / nviews / max_parallax_deg / ref_depth / mean_reproj |
| `viewer_gate_topdown_and_roi.png` | 门结果肉眼图(无红点=几何门扣不住任何 2° 放行点) |
| `manifest.json` | 输入/输出 SHA-256、相机、参数、峰值 RSS、LIMITATIONS |
| `run.stdout.log` / `run.resource.log` | 主脚本日志 / `/usr/bin/time -l` 资源 |
| `photometric_interval_probe.py` | 探索性光度区间探针(冻结样本,4K 图串行加载+释放) |
| `photometric_probe.jsonl` / `_summary.json` | 每点光度剖面 + 分类汇总(**探索性,见上诚实负面**) |
| `viewer_photometric_profiles.png` | 光度剖面(**已标 INCONCLUSIVE**) |
| `probe_manifest.json` / `probe.stdout.log` / `probe.resource.log` | 探针 manifest / 日志 / 资源 |
| `SHA256SUMS.txt` | 全部产物 SHA-256 |

复现:
```sh
/opt/homebrew/bin/python3.11 experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/dso_interval_gate.py
/opt/homebrew/bin/python3.11 experiments/u3_merge_prototypes_2026-07-18/03_dso_interval/photometric_interval_probe.py
```

内存自检:主脚本峰值 RSS **~0.13GB** / 6.5s;探针峰值 RSS **~1.34GB** / 93s(4K 图每点加载后释放,resident 上限 10 张)。
两者均内存安全,未逼近上限。
