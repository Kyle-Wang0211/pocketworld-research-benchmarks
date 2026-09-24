# Official PyTorch K Sweep

## Parameters

- device: `mps`
- process_res: `[476, 742]`
- k_values: `[1, 2, 3, 5, 10, 35]`
- save_arrays: `True`

## Attempts

| K | process_res | status | shape | forward ms | error |
|---:|---:|---|---|---:|---|
| 1 | 476 | failed | - | - | Degenerate covariance rank, Umeyama alignment is not possible |
| 2 | 476 | failed | - | - | Degenerate covariance rank, Umeyama alignment is not possible |
| 3 | 476 | success | 3x3x308x476 | 1083.7 | - |
| 5 | 476 | success | 5x3x308x476 | 1489.0 | - |
| 10 | 476 | success | 10x3x308x476 | 3937.1 | - |
| 35 | 476 | failed | - | - | Invalid buffer size: 15.36 GiB |
| 1 | 742 | failed | - | - | Degenerate covariance rank, Umeyama alignment is not possible |
| 2 | 742 | failed | - | - | Degenerate covariance rank, Umeyama alignment is not possible |
| 3 | 742 | success | 3x3x476x742 | 1455.5 | - |
| 5 | 742 | success | 5x3x476x742 | 5282.4 | - |
