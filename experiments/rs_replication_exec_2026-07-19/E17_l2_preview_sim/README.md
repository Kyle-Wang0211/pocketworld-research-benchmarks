# E17 — L2 渲染门"预览视效"模拟(display-only)

## 铁律(语义写死)
- **交付 PLY 永远全量**。本目录一切 `*_l2on_preview.ply` 只是"预览视效"对比件:模拟 L2 渲染门在**显示层**跳过 hidden 点后的视觉效果。生产语义 = display-only("NO point is deleted or moved"),导出/交付/上传路径绝不消费渲染门。
- 本目录不改任何生产文件、不 commit。数据源为 `data/pocketworld_captures/cap50|cap51/device_full_pull_2026-07-17/` 的只读拷贝。

## 规则(逐字抄自 lib/capture/ghost_view_filter.dart)
`hidden(p) = band15(p) ∧ ¬rescued(p)`(band15 = bit1 = kGhostHideBits;rescued = bit5)。
开关 `kGhostMaskViewFilter` 编译期常量 **默认 true(开门)**,`--dart-define=PW_GHOST_VIEW_FILTER=false` 暗关退路,永不接 UI。

## Mask 对齐(E2-A 疑虑的定论)
- native `ghost_mask.bin` = Points3D 序(cap50: 93,360 / cap51: 64,765)≠ 交付 PLY 点数——E2-A 的错位指的是它。
- **`ghost_view_mask.bin` = 交付点序 sidecar**(persist + 仲裁后重算,GhostDeliveredMaskRemap),长度 cap50: 92,849 / cap51: 64,392 == 交付 PLY,逐位对齐。本实验消费它,无需回放云。
- 交叉核对:band15 native→view 6013→6002 / 4927→4922(差值恰为 spatial+孤点过滤删掉的 511/373 点中的 band15 成员);bit5(rescued)719/469→719/468 已流入交付序(BIT5-FIX 生效证据)。

## 产物与 SHA256
见 `SHA256SUMS.txt`(每产物一行)。脚本:`e17_l2_sim.py`(解析+预览 PLY+指标)、`e17_render.py`(同 gauge 三视图渲染)。指标:`e17_metrics.json`、`e17_band_coverage.json`。

## 同 gauge 对比(compare_any,相对 experiments/rs_replication_exec_2026-07-19/)
- cap50:`compare_any.html?left=E17_l2_preview_sim/cap50_full_off.ply&right=E17_l2_preview_sim/cap50_l2on_preview.ply`
- cap51:`compare_any.html?left=E17_l2_preview_sim/cap51_full_off.ply&right=E17_l2_preview_sim/cap51_l2on_preview.ply`
- 静态渲染:`cap50_full_vs_l2on.png` / `cap51_full_vs_l2on.png`(俯视 / 立面 / 横截面,左 full 右 L2-on,同轴同 gauge,真彩直出,禁 Sim3)。

终审见 `E17_VERDICT.md`。
