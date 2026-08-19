# A4 真机打点操作手册(手机一有空档即插即测)

**目的**:拿到 A16 上 CasDiffMVS 的 ORT-WebGPU ms/帧——整个稠密优先架构唯一剩余的
go/no-go 数字。M3 锚点 528.7ms,A16 外推 1322–2115ms **横跨** 909ms 摊平预算线,
外推答不了,只有真机能答。**网络结构不随重训变 ⇒ 现在测的数对任何新权重都有效。**

## 资产(全部已在,未经真机验证)

- 端上 bench(iOS/Android 共用一份):研究仓 `research/casdiffmvs-official-replication-2026-08-17`
  分支,commit e2207c3("A4 的端上 bench 已写出——⚠️ 未经真机验证")。
- ONNX 模型:casdiffmvs_v5.onnx(6.7MB,已抢救到
  `progecttwo/_artifacts/casdiffmvs_onnx_20260818/`;可由 tools/export_onnx.py +
  C_long_ep31.ckpt 确定性复现;换新权重 = 重导一次)。
- ORT iOS 构建:卡在 ORT **issue #32147**(Dawn ObjCUtils.mm 与 ORT 强制 ARC 冲突),
  **补丁已验证可用**(08-17/18 移植战役)。构建时必须带该补丁。
- WebGPU EP 注意:必须 **ORT_ENABLE_BASIC**(EXTENDED+ 在 WebGPU 上静默产生非有限值,
  issue #32145,我们报的)。EP 名字是 "WebGpu"。

## 步骤

1. **构建**:iOS 原生 ORT + WebGPU EP,带 #32147 补丁(补丁与构建脚本在
   casdiffmvs-official-replication 分支的 A4 相关目录;构建产物签名走常规证书)。
2. **装机**:🔴 **用 `devicectl device install app`,绝对不用 `flutter install`**
   (后者先卸载——08-18 事故:8 个采集会话被永久删)。装前不需要备份(bench 是独立 app/
   harness,不碰采集数据),但若装到主 app 里则先按逐目录对账口径备份。
3. **测试**:🔴 拔线安全——启动 bench 后拔线,跑完看结果文件,不实时看日志。
   输入用 bench 自带的固定 feed(768×576 / num_view=10 口径);≥10 帧,丢首帧,取中位。
4. **记录三个数**:
   - **ms/帧**(中位)——判据见下
   - **内存峰值**——1.5GB 红线(iPhone 11 适配);M3 上 GPU buffer 约 1GB 量级
   - 热:连续 30 帧后 ms/帧 的漂移(热降频信号)

## 判据(拍 2 分钟/132 关键帧 ⇒ 摊平预算 909ms/帧)

| A16 实测 | 结论 |
|---|---|
| < 909ms | ✅ 拍摄期摊平成立,架构全线绿灯;iPhone 11 另测降档口径 |
| 909–1364ms | 🟡 3 分钟拍摄口径勉强;或降档(分辨率/num_view/关键帧密度)进预算 |
| > 1364ms | 🔴 摊平不成立——回到"拍完等稠密"形态,30s 承诺须重议 |

## 顺手可测(同一次插机)

- 融合(filter_depth)的手机侧:逐对几何检查 16ms/对是 M3 NumPy 口径,
  A16 C++ float32 重写的真实数字(工程化后)——本次可先不测,记录 CPU 型号即可。
- iPhone 11 若在手:同 bench 跑一遍,直接定下限机型档位。
