# Official DA3 source decode parity audit

- status: `warning_source_decode_not_byte_exact`
- shape match: `True`
- byte exact: `False`
- max abs uint8: `12`
- mean abs uint8: `0.5644947077041458`
- nonzero values: `15343998` / `30108672`

## Interpretation

Official DA3 loads source images through PIL; Dart package:image JPEG decode is not byte-exact. Preprocess pixel parity cannot be closed by resize math alone until source decode parity is addressed.

## Channels

| channel | min | max | mean abs | nonzero |
| --- | ---: | ---: | ---: | ---: |
| `R` | -12 | 11 | 0.567621 | 5070262 |
| `G` | -5 | 6 | 0.548020 | 5243458 |
| `B` | -8 | 10 | 0.577843 | 5030278 |
