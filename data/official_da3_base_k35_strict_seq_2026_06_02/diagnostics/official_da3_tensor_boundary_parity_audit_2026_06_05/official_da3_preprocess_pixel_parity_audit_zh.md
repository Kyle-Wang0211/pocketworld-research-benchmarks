# Official DA3 preprocess pixel parity audit

- status: `pass_exact_tensor_parity`
- official source mode: `photos_depth`
- sampled frames: `32`
- shape match: `True`
- tensor cache: `True`
- PNG lossless cache: `True`
- exact tensor match: `True`
- max abs normalized diff: `0.0`

## Interpretation

Dart now stores DA3's runtime input as pre-normalized float32 CHW tensors, so native PNG decode is no longer part of the official image-only path.
This audit still treats official preprocessing parity as unproven unless every sampled normalized tensor value matches exactly.

## Samples

| frame | input | codec | shape | max abs | mean abs |
| --- | --- | --- | --- | ---: | ---: |
| `cap-1` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-44` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-114` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-148` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-220` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-296` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-382` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-428` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-538` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-630` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-741` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-809` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-855` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-898` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-973` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1036` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1121` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1179` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1234` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1272` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1328` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1367` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1488` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1555` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1620` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1785` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1843` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1885` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-1959` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-2044` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-2135` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
| `cap-2219` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.000000 | 0.000000 |
