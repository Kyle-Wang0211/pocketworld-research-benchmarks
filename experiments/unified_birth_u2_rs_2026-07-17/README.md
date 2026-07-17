# U2-1 unified signed-visibility birth checkpoint

This checkpoint evaluates one source-agnostic pre-birth decision over the
frozen cap41 detector-free proposal population. It is a research milestone,
not a production candidate and not a claim of RealityScan parity.

## Frozen identity

- Device production baseline: 51,000 points, SHA-256
  `b1079c9984ca219ff2b97430e9f9a3cac9d3bfd02f7cd9255e42197091ada00b`.
- Detector-free proposals: 4,443 points, SHA-256
  `4d3058ce8bacfebc8f8bc55d0ee97b65cee01ec70e937ea48f8782096d058359`.
- Signed per-view evidence: SHA-256
  `36c957d82ef0a1421f03ba2d215dbcb79286ff52574a5df24e99489741aa6279`.
- Same device gauge, same production camera poses, and the frozen synchronized
  viewer are used for the comparison.

## Single global rule

A proposal is `DEFERRED` only when reliable `FREE_SPACE_CONFLICT` observations
strictly outnumber `AGREEMENT` observations. Occluded and uninformative views
abstain. The rule adds no numeric threshold, has no source-specific publication
gate, and does not delete a point after publication.

Result: 4,416 proposals certified, 27 deferred, 55,416 total visible points.
The original 51,000-point payload is the byte-exact prefix of the candidate.

## Reproduction

Run from the research worktree root:

```sh
/opt/homebrew/bin/python3.11 \
  experiments/unified_birth_u2_rs_2026-07-17/tools/unified_birth_controller.py \
  --baseline data/pocketworld_captures/cap41/device_2026-07-16/sfm_sparse.ply \
  --proposals experiments/unified_birth_u1_2026-07-17/runs/cap41_primary_evidence_v3_coarse_only/d_births_raw.ply \
  --evidence experiments/unified_birth_u1_2026-07-17/runs/cap41_u1_p3_any_certified_freespace_conflict/decisions.jsonl \
  --output-dir /tmp/pocketworld_cap41_u2_net_visibility_repro
```

The output directory must not already exist. The controller stages the complete
artifact set beside the destination and publishes it with macOS
`RENAME_EXCL`, so it cannot overwrite an existing result or an input alias.

Focused test:

```sh
/opt/homebrew/bin/python3.11 -m unittest \
  experiments/unified_birth_u2_rs_2026-07-17/tests/test_unified_birth_controller.py
```

## User visual verdict, 2026-07-17

The side-by-side true-color PLY review showed only a slight positive change near
the end of the bed and no scene-wide qualitative improvement over the previous
P0-P3 result. The user authorized preserving and pushing it as a research
checkpoint. It is explicitly **not approved for product integration** and must
not be described as a complete or substantial RealityScan-like improvement.
