# Latest Capture 414-Frame Benchmark

Capture: `cap_1779949415373229`

## DA3-Only Baseline

- Config: `DA3-BASE K35@476x742`
- Window size: 35
- Bridge overlap: 18
- Windows: 33
- Unique completed frames: 414 / 414
- Dense Sim3 tree bridge verification: passed

## DA3-Only vs DA3+MoGe Shadow Test

MoGe is evaluated as a pre-SAP uncertainty signal, not as a direct DA3 replacement.

| Metric | DA3 only | DA3 + MoGe | Delta |
|---|---:|---:|---:|
| bad_patch_auroc | 0.609210 | 0.617889 | +0.008680 |
| bad_patch_auprc | 0.335098 | 0.345844 | +0.010746 |
| ece | 0.006548 | 0.008755 | -0.002207 |
| brier | 0.182386 | 0.181470 | +0.000916 |
| error_at_80pct_coverage | 0.140692 | 0.138681 | +0.002011 |
| reprojection_p90_at_80pct_coverage | 0.452326 | 0.446823 | +0.005503 |
| coverage_at_fixed_error | 0.557019 | 0.588835 | +0.031816 |

Decision: MoGe remains research/shadow. It is promising enough to keep testing, but the advantage is not yet large enough to justify making it mandatory in the production SAP path.
