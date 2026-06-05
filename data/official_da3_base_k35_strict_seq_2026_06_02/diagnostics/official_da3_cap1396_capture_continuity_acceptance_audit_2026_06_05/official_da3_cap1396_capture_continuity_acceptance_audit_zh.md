# DA3 cap-1396 capture continuity acceptance audit

日期：2026-06-05

## 结论

- status: `cap1396_quality_accepted_but_continuity_breach_primary_suspect`
- goal complete: `False`

cap-1396 was eligible by still-image quality and official timestamp ordering, but it violates the existing Dart continuity warning thresholds before entering window_016 official downstream.

Official DA3-Streaming image-only chunking does not reject frames by AR/VIO continuity. A continuity gate is a mobile capture/product adaptation, not an official model-input requirement.

Add or simulate a Dart-side capture continuity quarantine for high-risk saved frames, then re-run DA3BASE_476x742_N35 on the same capture without using big-memory image-only export as the product gate.

## 大白话

- cap-1396 不是因为模糊或曝光差进来的；它的 accepted=True，kWindowWeight 约 0.687。
- 真正危险的是上一张到它的连续性：cap-1369 -> cap-1396，dt=4.467s，translation=0.410m，elevation jump=0.387rad。
- 它违反的连续性阈值是：timestampDeltaSeconds=4.467 > 2.000, translationStepM=0.410 > 0.250, elevationDeltaRad=0.387 > 0.250。
- 在 window_016 official downstream 审计里，它位于 slot 10，加入后 cumulative pose diag 到 0.677。
- 所以现在的判断不是 DA3 downstream merge 漏了去重，而是移动端采集/保留策略允许了一个画质可用但运动连续性差的帧进入单个 K35 window。

## Target Frame

| field | value |
|---|---:|
| frame | `cap-1396` |
| manifest index | 282 |
| accepted | `True` |
| quality score | 0.776 |
| kWindowWeight | 0.687 |
| timestamp delta | 4.467s |
| translation step | 0.410m |
| azimuth delta | 0.283rad |
| elevation delta | 0.387rad |
| high risk | `True` |

## Violations

| metric | value | threshold |
|---|---:|---:|
| `timestampDeltaSeconds` | 4.467 | > 2.000 |
| `translationStepM` | 0.410 | > 0.250 |
| `elevationDeltaRad` | 0.387 | > 0.250 |

## Pose/Depth Growth Around Target

| k | last frame | pose diag | npz bbox diag | npz minor extent | depth p95 | conf median |
|---:|---|---:|---:|---:|---:|---:|
| 10 | `cap-1369` | 0.297 | 1.430 | 0.678 | 2.607 | 6.082 |
| 11 | `cap-1396` | 0.677 | 1.513 | 0.745 | 2.598 | 6.113 |
| 12 | `cap-1413` | 0.834 | 1.638 | 0.900 | 2.598 | 5.875 |
| 13 | `cap-1417` | 0.868 | 1.753 | 1.007 | 2.603 | 5.797 |

## Code Path Findings

- `lib/capture/dome/dome_target_points.dart`: Hard rejects cover image sharpness, ROI sharpness, subject focus, focus/exposure stability, live radius outlier, angular velocity, brightness, and elevation; no previous-retained-frame dt/translation/elevation-delta hard gate is present.
- `lib/capture/dome/ring_buffer_cell.dart`: Diversity eviction includes timestamp distance in the novelty metric, so a long pause can make a frame more retainable instead of less retainable.
- `packages/aether_capture_services/lib/src/photo_bundle_pipeline_policy_service.dart`: The official DA3 window plan records continuityAudit warnings but does not filter official timestamp-ordered chunks by those warnings.
