#!/usr/bin/env bash
# Standard COLMAP front end on the 132 images, then triangulate against OUR known production poses, so the sparse
# model carries points3D — which is what OpenMVS's InterfaceCOLMAP expects. Pure official commands, no tuning.
set -uo pipefail
WS=/root/mvs_scene; SRC=/root/out_official
rm -rf $WS; mkdir -p $WS/images $WS/sparse_in $WS/sparse
cp -f $SRC/images/*.jpg $WS/images/
/venv/main/bin/python /root/write_sparse.py $SRC $WS/sparse_in_tmp 768 576 && mv $WS/sparse_in_tmp/sparse/* $WS/sparse_in/ && rmdir $WS/sparse_in_tmp/sparse $WS/sparse_in_tmp
C=/usr/local/bin/colmap
echo "[$(date +%H:%M:%S)] feature_extractor"
$C feature_extractor --database_path $WS/db.db --image_path $WS/images \
  --ImageReader.camera_model PINHOLE --SiftExtraction.use_gpu 1 > $WS/fe.log 2>&1; echo "  rc=$?"
echo "[$(date +%H:%M:%S)] exhaustive_matcher"
$C exhaustive_matcher --database_path $WS/db.db --FeatureMatching.use_gpu 1 > $WS/em.log 2>&1; echo "  rc=$?"
echo "[$(date +%H:%M:%S)] point_triangulator on known poses"
$C point_triangulator --database_path $WS/db.db --image_path $WS/images \
  --input_path $WS/sparse_in --output_path $WS/sparse > $WS/pt.log 2>&1; echo "  rc=$?"
grep -E "Point statistics|points" $WS/pt.log | tail -3 | cut -c1-120
$C model_converter --input_path $WS/sparse --output_path $WS/sparse_txt --output_type TXT > /dev/null 2>&1 || mkdir -p $WS/sparse_txt
echo "[$(date +%H:%M:%S)] SPARSE_DONE  points3D=$(ls -la $WS/sparse/points3D.bin | awk '{print $5}') bytes"
