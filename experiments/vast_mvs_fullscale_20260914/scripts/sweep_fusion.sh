#!/usr/bin/env bash
WS=/root/ws_colmap_hires
run() {
  /usr/local/bin/colmap stereo_fusion --workspace_path "$WS" --workspace_format COLMAP --input_type geometric \
    --output_path "$WS/p.ply" --StereoFusion.max_reproj_error "$1" --StereoFusion.max_depth_error "$2" \
    --StereoFusion.max_normal_error "$3" --StereoFusion.min_num_pixels "$4" --StereoFusion.max_num_pixels 100000 \
    > /dev/null 2>&1
  n=$(head -c 300 "$WS/p.ply" 2>/dev/null | strings | awk '/element vertex/{print $3}')
  echo "reproj $1  depth $2  normal $3  minpix $4  ->  ${n:-NA} points"
}
run 2 0.01 10 5
run 2 0.01 180 5
run 2 0.01 180 1
run 10 0.10 180 2
rm -f "$WS/p.ply" "$WS/p.ply.vis"
