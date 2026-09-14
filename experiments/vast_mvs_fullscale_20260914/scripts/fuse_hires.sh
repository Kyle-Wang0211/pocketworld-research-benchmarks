#!/usr/bin/env bash
# COLMAP's own fusion, defaults, with the one setting that matters here: the workspace must downsize the images to
# the depth-map size (images are 4032x3024, patch_match_stereo ran at 2000) or every pixel is rejected.
WS=/root/ws_colmap_hires
/usr/local/bin/colmap stereo_fusion --workspace_path "$WS" --workspace_format COLMAP --input_type geometric \
  --output_path "$WS/fused.ply" --StereoFusion.max_image_size 2000 --StereoFusion.cache_size 16 > "$WS/fusion.log" 2>&1
echo "rc=$?"
head -c 300 "$WS/fused.ply" 2>/dev/null | strings | awk '/element vertex/{print "points:", $3}'
grep -viE "^I2026" "$WS/fusion.log" | tail -2 | cut -c1-140
