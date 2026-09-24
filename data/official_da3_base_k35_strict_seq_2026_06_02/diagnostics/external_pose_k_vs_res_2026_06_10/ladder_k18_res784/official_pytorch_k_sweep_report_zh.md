# Official PyTorch K Sweep

## Parameters

- device: `mps`
- process_res: `[784]`
- k_values: `[18]`
- save_arrays: `True`

## Attempts

| K | process_res | status | shape | forward ms | error |
|---:|---:|---|---|---:|---|
| 18 | 784 | success | 18x3x448x784 | 26479.3 | - |
