#!/usr/bin/env bash
set -euo pipefail

readonly BIN=/root/colmap-4.1.1-src/build/src/colmap/exe/colmap
readonly OUTPUT=/root/colmap_official_dense_411_20260901_v4
readonly DENSE="$OUTPUT/dense"

test -d "$DENSE/images"
test -d "$DENSE/sparse"
mkdir -p "$OUTPUT/evidence"

echo "RESUME patch_match_stereo START $(date -Is)"
/usr/bin/time -v -o "$OUTPUT/evidence/patch_match_stereo.restart.time.txt" \
  "$BIN" patch_match_stereo \
    --workspace_path "$DENSE" \
    --workspace_format COLMAP
echo "RESUME patch_match_stereo DONE $(date -Is)"

echo "RESUME stereo_fusion START $(date -Is)"
/usr/bin/time -v -o "$OUTPUT/evidence/stereo_fusion.restart.time.txt" \
  "$BIN" stereo_fusion \
    --workspace_path "$DENSE" \
    --workspace_format COLMAP \
    --input_type geometric \
    --output_type PLY \
    --output_path "$DENSE/fused.ply"
echo "RESUME stereo_fusion DONE $(date -Is)"

sha256sum "$DENSE/fused.ply" > "$OUTPUT/evidence/fused.sha256"
stat -c '%n %s bytes' "$DENSE/fused.ply" > "$OUTPUT/evidence/fused.stat.txt"
LC_ALL=C grep -a -m1 '^element vertex ' "$DENSE/fused.ply" \
  > "$OUTPUT/evidence/fused.vertex.txt"
echo "PIPELINE COMPLETE $(date -Is)"
