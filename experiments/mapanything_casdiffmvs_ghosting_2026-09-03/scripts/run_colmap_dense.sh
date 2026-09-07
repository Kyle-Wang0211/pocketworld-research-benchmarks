#!/usr/bin/env bash
# Classical photometric PatchMatch (COLMAP dense) on the SAME 132 images, SAME COLMAP poses, SAME 768x576 as
# CasDiffMVS — the only variable is the depth algorithm (hand-crafted PatchMatch vs learned cost volume).
# Research probe only: needs CUDA, so it can never ship; it exists to falsify "every MVS sticks on white walls".
set -uo pipefail
WS=/root/ws_colmap_dense; SRC=/root/out_official
mkdir -p $WS/images $WS/stereo/depth_maps $WS/stereo/normal_maps $WS/stereo/consistency_graphs
cp -f $SRC/images/*.jpg $WS/images/ 2>/dev/null
/venv/main/bin/python /root/write_sparse.py $SRC $WS 768 576
/venv/main/bin/python - <<PY
lines=[l.strip() for l in open("/root/casdiffmvs_official_20260903/mvs_P16k/pair.txt") if l.strip()] if False else [l.strip() for l in open("/root/mvs_P16k/pair.txt") if l.strip()]
n=int(lines[0]); out=[]; i=1
for k in range(n):
    ref=int(lines[i]); t=lines[i+1].split(); m=int(t[0]); srcs=[int(t[1+2*j]) for j in range(m)]; i+=2
    out.append(f"{ref:08d}.jpg"); out.append(", ".join(f"{s:08d}.jpg" for s in srcs))
open("$WS/stereo/patch-match.cfg","w").write("\n".join(out)+"\n")
open("$WS/stereo/fusion.cfg","w").write("\n".join(out[::2])+"\n")
print("patch-match.cfg refs", n)
PY
echo "[$(date +%H:%M:%S)] patch_match_stereo (geometric consistency on)"
/usr/local/bin/colmap patch_match_stereo --workspace_path $WS --workspace_format COLMAP \
  --PatchMatchStereo.depth_min 2.5 --PatchMatchStereo.depth_max 11.0 \
  --PatchMatchStereo.max_image_size 768 --PatchMatchStereo.geom_consistency true \
  --PatchMatchStereo.filter true --PatchMatchStereo.num_samples 15 --PatchMatchStereo.num_iterations 5 \
  --PatchMatchStereo.gpu_index 0 > $WS/pms.log 2>&1
echo "  rc=$? depth maps=$(ls $WS/stereo/depth_maps/*.geometric.bin 2>/dev/null | wc -l)"
grep -viE "^I2026" $WS/pms.log | tail -3 | cut -c1-140
[ "$(ls $WS/stereo/depth_maps/*.geometric.bin 2>/dev/null | wc -l)" -gt 0 ] || { echo PMS_FAILED; exit 1; }
echo "[$(date +%H:%M:%S)] stereo_fusion"
/usr/local/bin/colmap stereo_fusion --workspace_path $WS --workspace_format COLMAP --input_type geometric \
  --output_path $WS/fused.ply --StereoFusion.max_num_pixels 100000 --StereoFusion.check_num_images 60 > $WS/fusion.log 2>&1
echo "  rc=$?"; head -c 200 $WS/fused.ply | strings | grep "element vertex"
/venv/main/bin/python /root/ply2bin_local.py $WS/fused.ply /root/bins_colmapdense colmapdense
echo "[$(date +%H:%M:%S)] DONE_colmapdense"
