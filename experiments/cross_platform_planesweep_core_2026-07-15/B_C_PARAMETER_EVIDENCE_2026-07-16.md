# B/C structural plane-sweep parameter evidence (2026-07-16)

This note separates externally supported design ranges from PocketWorld's
scene-frozen product thresholds. Passing cap40/41/50/51 is necessary evidence,
not proof that a numeric threshold is universal.

## Primary external references

- COLMAP 4.1.0 `PatchMatchOptions` (fixed tag):
  https://github.com/colmap/colmap/blob/4.1.0/src/colmap/mvs/patch_match_options.h
- COLMAP 4.1.0 `StereoFusionOptions` (fixed tag):
  https://github.com/colmap/colmap/blob/4.1.0/src/colmap/mvs/fusion.h
- COLMAP official weak-texture guidance:
  https://github.com/colmap/colmap/blob/4.1.0/doc/faq.rst#improving-dense-reconstruction-results-for-weakly-textured-surfaces
- Schoenberger et al., *Pixelwise View Selection for Unstructured Multi-View
  Stereo*, ECCV 2016, DOI 10.1007/978-3-319-46487-9_31:
  https://www.microsoft.com/en-us/research/publication/pixelwise-view-selection-for-unstructured-multi-view-stereo-2/
- Collins, *A Space-Sweep Approach to True Multi-Image Matching*, CVPR 1996:
  https://www.ri.cmu.edu/publications/a-space-sweep-approach-to-true-multi-image-matching/
- Furukawa's official PMVS2 documentation (author-maintained reference values):
  https://www.di.ens.fr/pmvs/documentation.html
- AliceVision/Meshroom official issue logs expose the then-default depth-map
  settings `minViewAngle=2`, `maxViewAngle=70`, `sgmMaxTCams=10`, and
  `refineMaxTCams=6`:
  https://github.com/alicevision/meshroom/issues/1306
- OpenCV's author-maintained StereoSGBM documentation describes the same
  *winner must beat runner-up* ambiguity check used by PocketWorld, normally
  as a 5--15 percent cost ratio. Its stereo cost is not numerically equivalent
  to a ZNCC difference, so this supports the mechanism but not `0.02/0.06`:
  https://docs.opencv.org/master/javadoc/org/opencv/calib3d/StereoSGBM.html

## Parameter-by-parameter status

| Decision | PocketWorld value | External comparison | Current status |
|---|---:|---|---|
| Floor patch | 7x7 over 3 cm metric support | PMVS2's author default is 7x7; COLMAP defaults to an 11x11 pixel window; AliceVision historically used half-window 4/3 in separate SGM/refine stages. Pixel and metric windows are not numerically interchangeable. | Externally corroborated sample count; metric footprint remains product-calibrated. |
| Wall patch | 9x9 over 6 cm metric support; strict also tests 12 cm | PMVS2 documents that a larger window is more stable but slower; COLMAP's official weak-texture guidance also recommends enlarging the patch window. | Externally supported direction, product-calibrated size. |
| Maximum source views | 10 | AliceVision SGM uses up to 10; COLMAP source selection commonly uses a configurable top-N set. | Externally corroborated range. |
| Floor minimum views | 3 | PMVS2's author default/suggestion is 3; COLMAP's final filter defaults to 2 consistent source images before a separate 5-pixel fusion gate. | Externally corroborated, but PocketWorld's all-pairs clique is stricter than either pipeline. |
| Wall minimum views | 4; strict/post gates 5-7 | PMVS2 explicitly suggests 4 or 5 views for weak texture, while warning about the accuracy/completeness trade-off. | Externally supported direction; 6-7 remains product empirical. |
| Floor minimum parallax | 5 degrees | COLMAP uses 1 degree for source selection and 3 degrees for filtering; AliceVision commonly starts at 2 degrees. | PocketWorld is stricter. |
| Wall parallax | 10 degrees; strict/post 18-21 degrees | Above general dense-MVS defaults. | Product anti-layer gate; generality not established by literature alone. |
| Maximum grazing angle | 72 degrees | AliceVision commonly exposes a 70-degree maximum view angle, but its camera-pair angle is not identical to PocketWorld's surface-incidence gate. | Directionally corroborated, not a numeric equivalence. |
| Floor ZNCC | 0.70 all-pairs clique | PMVS2's author default is NCC 0.70; COLMAP's `filter_min_ncc=0.1` is embedded in a bilateral PatchMatch likelihood plus geometric consistency. | The scalar is externally corroborated by PMVS2, but PocketWorld's all-pairs decision is stricter. |
| Wall ZNCC | 0.80; strict/post up to 0.92 | Same non-comparability as above. | Product-calibrated; must preserve wall coverage. |
| Texture stddev | floor 6.05 U8, wall 6.0 U8 | No portable official default: value depends on color space, bit depth, decoder, interpolation, and physical patch footprint. | Empirical. Floor 6.05 rejects cap50's decoder-only 6.024 view while retaining cap41's independently supported 6.061+ views; it is not a claimed universal constant. |
| Unique-depth margin | 0.02 ZNCC; strict 0.06 | OpenCV StereoSGBM likewise requires the best hypothesis to beat the runner-up, usually by a 5--15% cost ratio, while general MVS systems use other probability/geometric-consistency costs. | The ambiguity-rejection mechanism is externally corroborated; the PocketWorld ZNCC differences have no direct external numeric analogue. |
| Canonical NCC unit | 0.001 | No cited system exposes PocketWorld's cross-decoder ownership quantization. | Empirical cross-backend stability unit, not a universal vision threshold. |
| Boundary geometry tie-break | only a canonical 20-unit boundary within 0.001; center parallax at least 2x its normal minimum | Published systems combine photometric score with triangulation/view-angle evidence, but do not expose this exact deterministic tie rule. | Mechanism is externally motivated; 2x multiplier is product empirical and must pass held-out devices/scenes. |
| Competing depth offsets | floor +/-5 cm; wall +/-10 cm | Scene scale and plane uncertainty determine a meaningful offset. | Metric product prior; requires multi-scale scene validation. |
| Grid spacing | 10 cm selection, 5 cm refinement where needed | A product sampling-density choice, not a photometric threshold. | Coverage/time trade-off, validated per scene scale. |
| Tile size | floor 128, wall 64 candidates | Scheduling only; should not alter numerical results. | Performance parameter; exact-output parity required. |
| Image border | 2 px | A sampler-safety margin, not a reconstruction-quality constant. | Implementation bound; must scale if interpolation footprint changes. |
| Wall-family grouping | 15 degrees and 0.75 m | No direct analogue in the cited per-pixel MVS systems; the metric distance is scene-scale sensitive. | Product empirical; especially high generalization risk. |
| Owner dominance | score ratios 1.20-1.25, +2/+3 sites, sparse ratio 1.50 | No direct published equivalent because this is PocketWorld's one-plane-per-family birth authority. | Product empirical; four captures are insufficient to call universal. |

## Evidence-based conclusion

The current pipeline is more conservative than the compared general MVS
defaults on independent views and parallax. That is consistent with suppressing
ghost births, but increases the risk of losing weak-texture coverage. No single
published parameter set can be copied because PocketWorld evaluates known
metric planes with all-pairs ZNCC and explicit birth ownership, while COLMAP and
AliceVision estimate per-pixel depths with different likelihoods, regularizers,
and fusion stages.

The 6.05 U8 floor threshold is therefore accepted only if it retains the frozen
birth identity and owner decisions across cap40/41/50/51 with no runtime
increase. Additional captures with different lighting, exposure, JPEG decoder,
room size, and surface albedo remain necessary before calling it general.

## Generalization control for the current four captures

The four named captures are regression scenes, not a population sample. A
numeric value is therefore not promoted merely because one exact setting is
green. Before product admission, every empirical quality threshold must meet
both conditions below:

1. **Leave-one-capture-out stability:** a value/range selected without one of
   cap40/41/50/51 must preserve that omitted capture's frozen real births,
   owners, registered-view count, and original sparse bytes.
2. **Plateau rather than needle:** adjacent values on both sides must retain the
   same verdict, or the boundary must have an independent geometric reason and
   an explicit cross-decoder test. A single lucky decimal is classified as
   overfit and is not a production default.

This can establish robustness inside the available medium/large indoor scenes;
it still cannot establish universality across unseen devices, exposure modes,
surface materials, or room scales.

## Input limitation that must remain visible

cap51's SfM database and fed ledger contain 105 registered frames, but the
historical retained-photo bundle contains only 81 JPEGs. The B/C image fixture
therefore uses all 81 image/pose pairs that still exist, while the original
sparse cloud remains the 105/105-frame result. This is an old capture-retention
limitation, not an algorithmic view selector, and the run must not be described
as a 105-image plane-sweep validation. A post-E capture with all accepted JPEGs
durably retained is required for that claim.
