# Accepted full-room research baseline (2026-07-17)

This directory freezes the cap50/cap51 version visually accepted by the user as
the current best research baseline. It is the pre-1cm publication path:

1. preserve the complete device sparse cloud byte-for-byte;
2. append the original coarse/fine B/C structural births;
3. append the frozen true-colour D births.

No sparse point is filtered, deduplicated, recoloured, or moved. This milestone
improves visible correct structure; it does **not** claim to solve existing
floaters or ghost layers.

## Accepted identities

| Capture | Original | B/C births | D births | Total | Output SHA-256 |
| --- | ---: | ---: | ---: | ---: | --- |
| cap50 | 92,849 | 176 | 27,124 | 120,149 | `76b708b687ee7180cd6acb02170e3b3caae7fd5d084178ce52baf5b78f633767` |
| cap51 | 64,392 | 182 | 16,483 | 81,057 | `fc562406b9a4456c6b5e9cbd776dfd5c0d781bb54ca872d2288a1616b2d23666` |

The exact B/C outputs are:

- cap50: `e4d07c4e03e48c4bb46e1cba19f8a8a107f73fee71a5564a686b0ed54048be5f`
- cap51: `eb435998415ac118187ceba9e7992f38083b87891c9cea9453f5cf90f53972e6`

The native library used for the replay was:

`1c7ce574f144bfa0870f62368a1dc825417234061e6cfa9c992fb9fbc5784b95`

The exact Dart quality fixture manifest was:

`1521f570178d5d506c1b1a547bc927e766ed6d53f13cd19b2f287cc71f50009a`

## Source identity

`source_snapshot/bcd_structural_quality_runner.dart` is the exact runner that
generated the accepted B/C clouds. Its SHA-256 is:

`7868bf272139ac1576a1ab843ee9d20d19a411311cde284c952f4e3b64b88eba`

It differs from the later rejected runner only by publishing the already
verified coarse/fine winner births instead of replaying every selected plane on
a 1cm grid. `source_snapshot/bcd_compare_ply_export.dart` is the exact exporter,
SHA-256:

`2e58b1137243cd013f74be9f7b2d1b92ab9ef1dcd8c5bbc3d53408ea09e382f8`

## Rebuild and inspect

`rebuild_initial_fullroom_candidate.py` verifies every frozen layer SHA, maps
the B/C metric births back into the device gauge using the immutable sparse
prefix, and writes the additive cloud. `compare_fullroom.html` renders the
accepted cloud beside the device original with one synchronized camera.

The authoritative human verdict is recorded in
`USER_VISUAL_ACCEPTANCE_2026-07-17.json`.
