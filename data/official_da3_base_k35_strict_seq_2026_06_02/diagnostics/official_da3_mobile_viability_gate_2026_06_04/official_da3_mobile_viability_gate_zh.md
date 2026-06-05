# Official DA3 mobile viability gate

日期：2026-06-04

## 目的

这份 gate 专门回答一个问题：

> DA3-BASE / CoreML / K35@476x742 是否真的适合 PocketWorld 的手机、平板、笔记本产品路径？

它和 A100/H100 reference gate 是两件事：

- A100/H100 gate：只用来验证官方 PyTorch full same-resolution K35 是否也厚，是一次性 research 判案。
- mobile viability gate：用真实目标设备上的 APP artifact 判断 DA3 是否能继续作为产品候选。

如果 A100 gate 关闭但 mobile viability gate 失败，产品仍然不能押 DA3。

如果 A100 gate 未关闭但 mobile viability gate 在目标设备上稳定通过，DA3 仍可作为产品候选继续推进，同时保留官方 parity gap 说明。

## 新增脚本

脚本：

`tools/python/da3_mobile_viability_gate.py`

读取：

- `stages/depth/depth_index.json`
- `stages/depth/da3_real_device_audit.json`
- `stages/pointcloud/official_pointcloud_report.json`

或直接传入 `--depth-index` / `--real-device-audit` / `--pointcloud-report`。

输出：

- `schema_version: aether_da3_mobile_viability_gate_report_v1`
- `status: pass | warning | fail`
- official baseline checks
- real-device telemetry summary
- caller-supplied latency / memory threshold checks

设计原则：

- 不因为 Mac research executor 跑通就给 mobile pass。
- 没有真机 telemetry 时，real-device mode 直接 fail，research mode 只 warning。
- 没有显式 latency / memory threshold 时，最多 warning。
- 产品 pass 必须同时满足 official baseline、真机 telemetry、目标设备阈值。

## Research 样例验证

输入：

`data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_official_save_overlap18_official_postprocess/depth_index.json`

命令：

```bash
/usr/bin/python3 tools/python/da3_mobile_viability_gate.py \
  --mode research \
  --depth-index data/official_da3_base_k35_strict_seq_2026_06_02/da3_seq_k35_coreml_official_save_overlap18_official_postprocess/depth_index.json \
  --out data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_mobile_viability_gate_2026_06_04/mobile_viability_gate_research_sample_report.json
```

输出：

`data/official_da3_base_k35_strict_seq_2026_06_02/diagnostics/official_da3_mobile_viability_gate_2026_06_04/mobile_viability_gate_research_sample_report.json`

结果：

- `status: warning`
- DA3-BASE / Apache-2.0 / K35@476x742：pass
- depth stage completed 414 / 414 frames：pass
- real-device audit missing：warning
- official pointcloud report missing for this sample path：warning
- explicit product thresholds missing：warning

这个结果是正确的。它说明 Research 样例有 baseline 价值，但不能证明手机/平板/笔记本产品可行。

## 真机运行方式

真机 capture 完成后，对 APP capture 目录运行：

```bash
/usr/bin/python3 tools/python/da3_mobile_viability_gate.py \
  --mode real-device \
  --capture-dir /path/to/app_capture_dir \
  --max-window-p95-ms 30000 \
  --max-window-max-ms 60000 \
  --max-rss-peak-mb 5000 \
  --min-available-memory-mb 500 \
  --fail-on-serious-thermal \
  --out /path/to/app_capture_dir/stages/depth/da3_mobile_viability_gate_report.json
```

阈值解释：

- `--max-window-p95-ms`：大多数 DA3 window 的推理耗时上限。
- `--max-window-max-ms`：最慢 DA3 window 的推理耗时上限。
- `--max-rss-peak-mb`：APP 进程 RSS 峰值上限。
- `--min-available-memory-mb`：iOS jetsam 可用内存下限。
- `--fail-on-serious-thermal`：设备达到 serious/critical thermal 就不算产品通过。

上面的数值只是示例，不是最终产品 SLA。最终 SLA 需要按目标设备和用户体验定义：

- iPhone baseline
- iPad baseline
- MacBook baseline
- 低电量 / 热机 / 后台恢复场景

## 判读规则

### pass

可以说：

- 这次 capture 在该设备和阈值下通过 DA3 mobile viability gate。
- DA3-BASE / CoreML / K35@476x742 仍可作为产品候选。

不能说：

- DA3 已经 100% 官方 parity。
- full same-resolution PyTorch K35 gate 已关闭。

### warning

可以说：

- 这份证据有研究价值，但不足以证明产品可行。

常见原因：

- 只有 Research executor，没有真机 telemetry。
- 没有指定产品 latency / memory 阈值。
- 缺 `official_pointcloud_report.json`，只能判断 depth stage，不能判断 downstream baseline。

### fail

可以说：

- 该设备 / 该阈值 / 该 capture 下，DA3 不满足产品 gate。

如果多台目标设备反复 fail，尤其是：

- K35 window 不能完成；
- RSS / jetsam headroom 不达标；
- thermal serious/critical；
- p95 / max latency 超产品上限；
- official core-frame pointcloud baseline 不成立；

则 DA3 应该从 PocketWorld 产品候选中降级或淘汰。

## 和当前结论的关系

当前 `89.01 GiB` / `15.36 GiB` 是官方 PyTorch/MPS reference gate 的内存问题，不是 mobile viability gate 的结果。

PocketWorld 是否继续使用 DA3，最终要看：

1. 官方复刻链路是否诚实：DA3-BASE、K35@476x742、official core-frame npz downstream、no hidden cleanup。
2. 目标设备是否过线：真机 telemetry + latency/memory/thermal 阈值。
3. 几何质量是否可接受：单 window 厚层、跨 window residual、最终 PLY/mesh 是否达到产品要求。

因此现在不能因为 A100 gate 未关闭就直接抛弃 DA3；也不能因为 Research executor 跑完整 414 张就宣布 DA3 产品可行。

正确下一步是：

- 如果要判 upstream：租 A100/H100 短时关闭 PyTorch K35 full-res reference gate。
- 如果要判产品：拿 iPhone/iPad/MacBook 跑 APP capture，然后用 `da3_mobile_viability_gate.py` 出报告。
