# WGSL 匹配器:逐字节无损 + 追平 Metal(2026-09-03/04)

**目标**(用户铁令):三端(iOS/安卓/鸿蒙)公用**同一套** WGSL/Dawn 匹配器实现,iOS 不许保留
Metal 快路;速度必须尽全力追平甚至超越苹果原生。**所有改动必须逐字节无损。**

## 结论速览
| 阶段 | 8192² 一对 GPU p50 | 对 native Metal |
|---|---|---|
| 起点(f32 MMA + tint 健壮性代码) | 13.87 ms | 2.6× |
| + 混合精度(f16 操作数 / f32 累加器) | 9.94 | 1.9× |
| + 关 tint 健壮性代码 | **7.9-8.7** | **~1.3-1.6×** |
| native Metal(参照) | 5.2-6.6 | 1.0 |
**累积 −43%,全程逐字节无损。**

## 门(每一刀都重跑,任何一处不逐字节即失败)
- `fair_match_parity_suite.sh`:19 构造案例 × 三重金标准(pairs/OutAB/OutBA SHA);
- 全量闸:真实设备会话 **696 对**(20 帧库 162 + 51 帧库 534)逐字节;
- guided 两档对拍 Metal v1:**148 案例 / 79,082 对**逐字节;
- ABI 测试:probe_batch / 描述子驻留 / 参数校验 / guided,0 失败。

## 关键发现
1. **Metal 快 2.4× 的唯一原因**:它用 `simdgroup_matrix<half>` 操作数 + `<float>` 累加器。
   u8 ≤255 在 f16 中精确、逐积 ≤65,025 与 K=128 总和 ≤262,144 在 f32 24 位尾数内精确
   ⇒ **既精确又拿 half 速率**。
2. **WGSL 侧不是不支持,是 Dawn 没登记**:语言层 `core.def:2858` 早有
   `implicit(T: f16, TR: f32_f16)` 重载,tint 的 MSL 生成端类型无关,Apple 硬件/MSL 支持,
   但 `metal/PhysicalDeviceMTL.mm` **把配置表硬编码成两条**(f32→f32、f16→f16),
   `ShaderModule.cpp:1728` 又拿 shader 去比对这张表 ⇒ 混合形态在校验期被拒。
   补一条即可(见 `dawn_patch/`)。**Vulkan 后端从驱动动态枚举,安卓/鸿蒙无需改动。**
3. **tint 健壮性代码**在 MMA 最内层循环生成边界检查 + 矩阵零填充;我们的索引由构造在界内
   (主机把描述子表补齐到 128 行倍数并零填充),关掉 `disable_robustness` 再 −28%。

## 判死的路(每条都有机制,别再试)
- **f16→f16**(纯半精度):SIFT 的 best−second 中位仅 823(占 best 0.3%),f16 累加误差界
  20,480 ⇒ 候选集中位 7852/8192,两阶段回退退化为全精确。
- **半字节拆分做精确整数**:nibble 逐积 ≤225、K=8 部分和 ≤1800 在 f16 内精确,但需 4 趟 MMA
  = 比 f32 慢 2.9×。
- **向量化 B staging(vec4<f16>)**:只有设备端读被向量化,写共享内存仍是 4 次标量写
  (`subgroupMatrixLoad` 只收标量数组)⇒ 慢 3ms。
- **手工展开 K 循环**:生成的 MSL 里矩阵数组确实消失,但速度不变(Metal 编译器本已处理)。
- **线程切分重平衡**(2 线程/行 与 1 线程/2 行):两个方向分别慢 1.0ms 与 0.3ms
  ⇒ 现役 128 扫行/32 扫列/352 预取已是平衡点。
- **分块定价去开销**:固定提交开销实测仅 0.035ms,不是杠杆。
- **矩阵零填充**:8×8 矩阵摊到 32 lane = 每 lane 2 个寄存器写,量级可忽略。

## 复现
```
bash tools/fair_match_build.sh <out>                       # 台架(含 native 参照臂)
bash tools/pwofficial_gpu_match_dawn_host_build.sh <out2>   # 生产 TU 的 host 臂
bash tools/fair_match_parity_suite.sh <out2> <work> <label> # 19 案例三重金标准
env BIN=<out2> FULLGATE_DB=<会话 db> MAXF=20 LABEL=x bash tools/pwofficial_gpu_match_dawn_fullgate.sh
<out>/sgmatrix_probe                                        # 枚举本机子组矩阵配置
```
计时纪律:镜像 ABBA / 交替多轮 + native 括号;括号自身差 >1ms 的轮次作废
(实测 HydraRenderingService 常驻 96% 时括号能飘 2-4ms,GPU 时间戳也救不了 —— 它抢的就是 GPU)。

## 产品侧对应
生产 TU 与分发层已进 `pocketworld` 仓 `vendor/official_sfm/src/`(默认后端 dawn、默认核 mixed,
env `OFFICIAL_AETHER_MATCH_BACKEND=metal` / `..._DAWN_KERNEL=plain` 可切回做单变量 A/B)。
