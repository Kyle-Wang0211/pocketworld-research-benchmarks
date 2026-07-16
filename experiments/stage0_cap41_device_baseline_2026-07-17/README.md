# stage0 — cap41 device-exact 真彩基线(2026-07-17)

按 2026-07-16 交接文件 §14 阶段 0 执行。**本目录是后续所有 cap41 对照的左侧权威。**

## 数据来源(全部设备原件,零 host replay、零 Sim3)

- `../../data/pocketworld_captures/cap41/device_2026-07-16/sfm_sparse.ply`
  - SHA-256 `b1079c9984ca219ff2b97430e9f9a3cac9d3bfd02f7cd9255e42197091ada00b`
  - 51,000 点,binary_little_endian,float XYZ + uchar RGB,载荷逐字节 15B×51000 对齐
  - 与用户手机展示"约 51,000 点"一致
- `sfm_sparse_metric.npz`:同 51,000 点的米制版(设备产物)→ 定出 **1 ply unit = 3.495cm**
- meta:95/102 注册,reproj 0.9716px,solve 25.3s,`delivered_points 51373` vs PLY 51000(差 373,待设备侧对账 ⚠️)

## 核验结论

- 0 NaN;仅 22 个灰点(0.04%)= 真彩确认
- up=+Y(95 个相机中心中位高度 = 地板上 1.77m,手持高度合理)
- **地板区 Y 分层:-27.95 / -28.31 / -28.86(间距 1.3cm / 3.2cm)——落在 cap47 双层地板病理带(2-3.5cm)内。哪一层是真地板是 stage-1.5 分桶问题,本目录不预设。**
- 床品面(床垫贴地式)峰 Y=-25.60

## 文件

- `cap41_device_baseline_viewer.html` — 交互 viewer(验收面),经 `stage0-viewer` 服务打开:
  `http://localhost:8642/experiments/stage0_cap41_device_baseline_2026-07-17/cap41_device_baseline_viewer.html`
- `views.json` — **四个冻结视角(overview / floor_edge / wall_edge / bed)的唯一参数源**。
  任何 cap41 候选云必须复用这四个相机逐参数不变,才允许与本基线并排对照。
- `render_views.py` — 零依赖离线渲染器(同源消费 views.json);候选云复用:
  `python3 render_views.py <candidate.ply> <outdir>`(RENDER_LABEL 环境变量改标签)
- `view_*.png` — 基线四视角存档(与浏览器渲染已目检一致)
- `verification.json` — 完整核验数字

## 规则

1. 视角参数冻结:改 views.json = 作废全部历史对照,必须用户签决。
2. 候选云与基线同坐标系(device gauge)直出,禁止任何对齐/缩放后再比。
3. 本目录只描述"设备原版是什么",不含任何候选/改进判断。
