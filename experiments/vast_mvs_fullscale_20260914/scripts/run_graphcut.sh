#!/usr/bin/env bash
# Visibility graph-cut on the official CasDiffMVS depths, on the rented box.
#   run_graphcut.sh <voxel_m> <tag>
# 1) official filter.py fusion + per-point visibility -> fused.ply/.vis (+ full-res official_full.ply once)
# 2) COLMAP delaunay_mesher (Labatut visibility graph cut)
# 3) mesh as arbiter -> keep/drop each of the full-res official points
set -uo pipefail
VOX=${1:?voxel in metres}; TAG=${2:?tag}
PY=/venv/main/bin/python; SRC=/root/out_official; WS=/root/ws_$TAG
mkdir -p $WS
echo "[$(date +%H:%M:%S)] fusion + visibility, voxel ${VOX}"
$PY /root/official_fuse_vis.py $SRC /root/mvs_P16k/pair.txt $WS $VOX 2>&1 | grep -v "^ref " | tail -6
[ -f $WS/fused.ply.vis ] || { echo "FUSION_FAILED"; exit 1; }
$PY /root/write_sparse.py $SRC $WS 768 576
echo "[$(date +%H:%M:%S)] delaunay graph cut"
/usr/local/bin/colmap delaunay_mesher --input_path $WS --input_type dense --output_path $WS/mesh.ply \
  --DelaunayMeshing.max_depth_dist 0.002 --DelaunayMeshing.num_threads -1 > $WS/delaunay.log 2>&1
grep -E "Triangulation has|Elapsed time|Maximum resident" $WS/delaunay.log | tail -3
[ -s $WS/mesh.ply ] || { echo "MESH_FAILED"; tail -5 $WS/delaunay.log; exit 1; }
echo "[$(date +%H:%M:%S)] filtering the full-resolution official cloud with the mesh"
$PY /root/mesh_filter_full.py $WS/mesh.ply $WS/official_full.ply /root/bins_$TAG $TAG 0.01 2>&1 | grep -v "^  " | tail -6
echo "[$(date +%H:%M:%S)] DONE_$TAG"
