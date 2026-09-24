# Official DA3 input cache manifest

- source mode: `source_highres`
- status: `official_input_cache_exported`
- sample count: `8`
- Dart tensor exact match: `False`
- Dart tensor max abs normalized: `0.03501415252685547`

## Interpretation

Dart runtime tensor is not byte-exact with official source_highres preprocessing; max normalized diff is 0.03501415252685547.

## Samples

| frame | source wh | output wh | compare | max abs |
| --- | --- | --- | --- | ---: |
| `cap-1` | `[4224, 2376]` | `[504, 280]` | `different` | 0.035014 |
| `cap-257` | `[4224, 2376]` | `[504, 280]` | `different` | 0.035014 |
| `cap-619` | `[4224, 2376]` | `[504, 280]` | `different` | 0.035014 |
| `cap-918` | `[4224, 2376]` | `[504, 280]` | `different` | 0.035014 |
| `cap-1224` | `[4224, 2376]` | `[504, 280]` | `different` | 0.035014 |
| `cap-1494` | `[4224, 2376]` | `[504, 280]` | `different` | 0.035014 |
| `cap-1870` | `[4224, 2376]` | `[504, 280]` | `different` | 0.035014 |
| `cap-2219` | `[4224, 2376]` | `[504, 280]` | `different` | 0.035014 |
