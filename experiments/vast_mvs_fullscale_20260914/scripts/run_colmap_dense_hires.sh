#!/usr/bin/env bash
# COLMAP dense the way it is actually used: NATIVE 4032x3024 images, max_image_size 2000 (the usual community
# setting), COLMAP's own consistency graphs and its own stereo_fusion. Nothing tuned, all defaults except the
# resolution cap and the explicit depth range (our sparse model carries no points3D).
set -uo pipefail
WS=/root/ws_colmap_hires; SRC=/root/mvs_P16k; C=/usr/local/bin/colmap
rm -rf $WS; mkdir -p $WS/images $WS/stereo/depth_maps $WS/stereo/normal_maps $WS/stereo/consistency_graphs
cp -f $SRC/images/*.jpg $WS/images/
/venv/main/bin/python /root/write_sparse.py $SRC $WS 4032 3024
/venv/main/bin/python - <<PY
lines=[l.strip() for l in open("$SRC/pair.txt") if l.strip()]
n=int(lines[0]); out=[]; i=1
for k in range(n):
    ref=int(lines[i]); t=lines[i+1].split(); m=int(t[0]); srcs=[int(t[1+2*j]) for j in range(m)]; i+=2
    out.append(f"{ref:08d}.jpg"); out.append(", ".join(f"{s:08d}.jpg" for s in srcs))
open("$WS/stereo/patch-match.cfg","w").write("\n".join(out)+"\n")
open("$WS/stereo/fusion.cfg","w").write("\n".join(out[::2])+"\n")
print("patch-match.cfg refs", n)
PY
echo "[$(date +%H:%M:%S)] patch_match_stereo @2000px"
$C patch_match_stereo --workspace_path $WS --workspace_format COLMAP \
  --PatchMatchStereo.max_image_size 2000 --PatchMatchStereo.depth_min 2.5 --PatchMatchStereo.depth_max 11.0 \
  --PatchMatchStereo.geom_consistency true --PatchMatchStereo.filter true \
  --PatchMatchStereo.write_consistency_graph true --PatchMatchStereo.gpu_index 0 > $WS/pms.log 2>&1
echo "  rc=$? geometric=$(ls $WS/stereo/depth_maps/*.geometric.bin 2>/dev/null | wc -l) graphs=$(ls $WS/stereo/consistency_graphs/*.bin 2>/dev/null | wc -l)"
grep -viE "^I2026" $WS/pms.log | tail -3 | cut -c1-140
echo "[$(date +%H:%M:%S)] stereo_fusion (COLMAP defaults)"
$C stereo_fusion --workspace_path $WS --workspace_format COLMAP --input_type geometric \
  --output_path $WS/fused.ply > $WS/fusion.log 2>&1
echo "  rc=$?"; head -c 200 $WS/fused.ply | strings | grep "element vertex"
/venv/main/bin/python /root/ply2bin_local.py $WS/fused.ply /root/bins_hires colmap_hires
echo "[$(date +%H:%M:%S)] DONE_hires"
