# Official DA3 preprocess pixel parity audit

- status: `warning_tensor_not_exact_official_input_processor`
- official source mode: `canonical_source_rgb`
- sampled frames: `1`
- shape match: `True`
- tensor cache: `True`
- PNG lossless cache: `True`
- exact tensor match: `False`
- max abs normalized diff: `0.017429232597351074`

## Interpretation

Dart now stores DA3's runtime input as pre-normalized float32 CHW tensors, so native PNG decode is no longer part of the official image-only path.
This audit still treats official preprocessing parity as unproven unless every sampled normalized tensor value matches exactly.

## Samples

| frame | input | codec | shape | max abs | mean abs |
| --- | --- | --- | --- | ---: | ---: |
| `cap-1` | `float32_chw_tensor` | `PNG` | `[3, 280, 504]` | 0.017429 | 0.000000 |
