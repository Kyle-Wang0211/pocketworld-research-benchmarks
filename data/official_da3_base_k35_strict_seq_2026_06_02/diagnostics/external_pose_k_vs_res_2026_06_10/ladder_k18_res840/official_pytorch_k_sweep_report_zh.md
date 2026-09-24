# Official PyTorch K Sweep

## Parameters

- device: `mps`
- process_res: `[840]`
- k_values: `[18]`
- save_arrays: `True`

## Attempts

| K | process_res | status | shape | forward ms | error |
|---:|---:|---|---|---:|---|
| 18 | 840 | success | 18x3x476x840 | 32283.6 | - |
