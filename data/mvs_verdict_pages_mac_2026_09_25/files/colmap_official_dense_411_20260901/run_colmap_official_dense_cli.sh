#!/usr/bin/env bash
set -euo pipefail

readonly BIN=/root/colmap-4.1.1-src/build/src/colmap/exe/colmap
readonly INPUT=/root/repro_official_colmap_native_20260901
readonly OUTPUT=/root/colmap_official_dense_411_20260901_v4
readonly DENSE="$OUTPUT/dense"

if [[ -e "$OUTPUT" ]]; then
  echo "Refusing to overwrite existing output: $OUTPUT" >&2
  exit 90
fi

mkdir -p "$DENSE" "$OUTPUT/evidence"
{
  "$BIN" version
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
  nvcc --version | tail -n 1
  git -C /root/colmap-4.1.1-src rev-parse HEAD
} > "$OUTPUT/evidence/environment.txt" 2>&1

find "$INPUT/images" -maxdepth 1 -type f -printf '%f\n' | LC_ALL=C sort \
  > "$OUTPUT/evidence/ordered_images.txt"
sha256sum "$INPUT/sparse/cameras.bin" "$INPUT/sparse/images.bin" \
  "$INPUT/sparse/points3D.bin" > "$OUTPUT/evidence/sparse.sha256"

echo "STAGE image_undistorter START $(date -Is)"
/usr/bin/time -v -o "$OUTPUT/evidence/image_undistorter.time.txt" \
  "$BIN" image_undistorter \
    --image_path "$INPUT/images" \
    --input_path "$INPUT/sparse" \
    --output_path "$DENSE" \
    --output_type COLMAP
echo "STAGE image_undistorter DONE $(date -Is)"

echo "STAGE patch_match_stereo START $(date -Is)"
/usr/bin/time -v -o "$OUTPUT/evidence/patch_match_stereo.time.txt" \
  "$BIN" patch_match_stereo \
    --workspace_path "$DENSE" \
    --workspace_format COLMAP
echo "STAGE patch_match_stereo DONE $(date -Is)"

echo "STAGE stereo_fusion START $(date -Is)"
/usr/bin/time -v -o "$OUTPUT/evidence/stereo_fusion.time.txt" \
  "$BIN" stereo_fusion \
    --workspace_path "$DENSE" \
    --workspace_format COLMAP \
    --input_type geometric \
    --output_type PLY \
    --output_path "$DENSE/fused.ply"
echo "STAGE stereo_fusion DONE $(date -Is)"

sha256sum "$DENSE/fused.ply" > "$OUTPUT/evidence/fused.sha256"
stat -c '%n %s bytes' "$DENSE/fused.ply" > "$OUTPUT/evidence/fused.stat.txt"
echo "PIPELINE COMPLETE $(date -Is)"
