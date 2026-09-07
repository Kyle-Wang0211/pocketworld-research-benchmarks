#!/usr/bin/env bash
# THE community pipeline, official commands only, no hand-written models and no substituted stages:
#   COLMAP feature_extractor -> exhaustive_matcher -> mapper -> image_undistorter
#   OpenMVS InterfaceCOLMAP -> DensifyPointCloud -> ReconstructMesh -> RefineMesh -> TextureMesh
# Native 4032x3024 input, undistorted to 2000 px (the usual community setting). All defaults otherwise.
set -uo pipefail
W=/root/community; SRC=/root/mvs_P16k; C=/usr/local/bin/colmap; B=/usr/local/bin/OpenMVS
mkdir -p $W/images
[ -f $W/db.db ] || cp -f $SRC/images/*.jpg $W/images/
if [ ! -f $W/db.db ]; then
  echo "[$(date +%H:%M:%S)] feature_extractor"
  $C feature_extractor --database_path $W/db.db --image_path $W/images \
     --ImageReader.camera_model PINHOLE --ImageReader.single_camera 1 --FeatureExtraction.use_gpu 1 > $W/1_fe.log 2>&1
  echo "  rc=$?"
  echo "[$(date +%H:%M:%S)] exhaustive_matcher"
  $C exhaustive_matcher --database_path $W/db.db --FeatureMatching.use_gpu 1 > $W/2_em.log 2>&1
  echo "  rc=$?"
fi
echo "[$(date +%H:%M:%S)] mapper (COLMAP's own SfM)"
mkdir -p $W/sparse
$C mapper --database_path $W/db.db --image_path $W/images --output_path $W/sparse > $W/3_mapper.log 2>&1
echo "  rc=$? models=$(ls $W/sparse | tr '\n' ' ')"
$C model_analyzer --path $W/sparse/0 2>&1 | grep -viE "^I2026" | head -6 | cut -c1-100
echo "[$(date +%H:%M:%S)] image_undistorter -> dense workspace @2000px"
$C image_undistorter --image_path $W/images --input_path $W/sparse/0 --output_path $W/dense \
   --output_type COLMAP --max_image_size 2000 > $W/4_undist.log 2>&1
echo "  rc=$? $(ls $W/dense 2>/dev/null | tr '\n' ' ')"
echo "[$(date +%H:%M:%S)] InterfaceCOLMAP"
$B/InterfaceCOLMAP -i $W/dense -o $W/scene.mvs -w $W > $W/5_iface.log 2>&1
echo "  rc=$? $(ls -la $W/scene.mvs 2>/dev/null | awk '{printf "%.1f MB", $5/1048576}')"
echo "[$(date +%H:%M:%S)] DensifyPointCloud"
$B/DensifyPointCloud $W/scene.mvs -w $W > $W/6_densify.log 2>&1
echo "  rc=$? $(ls -la $W/scene_dense.ply 2>/dev/null | awk '{printf "%.1f MB", $5/1048576}')"
[ -f $W/scene_dense.mvs ] || { echo DENSIFY_FAILED; tr '\r' '\n' < $W/6_densify.log | tail -3 | cut -c1-160; exit 1; }
echo "[$(date +%H:%M:%S)] ReconstructMesh"
$B/ReconstructMesh $W/scene_dense.mvs -w $W > $W/7_mesh.log 2>&1; echo "  rc=$?"
echo "[$(date +%H:%M:%S)] RefineMesh"
$B/RefineMesh $W/scene_dense_mesh.mvs -w $W > $W/8_refine.log 2>&1; echo "  rc=$?"
echo "[$(date +%H:%M:%S)] TextureMesh"
$B/TextureMesh $W/scene_dense_mesh_refine.mvs -w $W > $W/9_tex.log 2>&1; echo "  rc=$?"
ls -la $W/*.ply $W/*.png 2>/dev/null | awk '{printf "  %.1f MB %s\n", $5/1048576, $9}'
echo "[$(date +%H:%M:%S)] COMMUNITY_DONE"
