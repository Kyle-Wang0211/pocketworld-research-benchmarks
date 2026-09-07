#!/usr/bin/env bash
# The community pipeline's COLMAP half, on the NATIVE 4032x3024 images, official commands only:
#   feature_extractor -> exhaustive_matcher -> point_triangulator (on our known production poses) -> image_undistorter
# image_undistorter is the step that produces the dense workspace OpenMVS's InterfaceCOLMAP expects; I skipped it
# last time.
set -uo pipefail
W=/root/mvs_hires; SRC=/root/mvs_P16k; C=/usr/local/bin/colmap
rm -rf $W; mkdir -p $W/images $W/sparse_in
cp -f $SRC/images/*.jpg $W/images/
/venv/main/bin/python /root/write_sparse.py $SRC $W/tmp 4032 3024 && mv $W/tmp/sparse/* $W/sparse_in/ && rm -rf $W/tmp
echo "[$(date +%H:%M:%S)] feature_extractor (native 4032)"
$C feature_extractor --database_path $W/db.db --image_path $W/images \
   --ImageReader.camera_model PINHOLE --FeatureExtraction.use_gpu 1 > $W/fe.log 2>&1; echo "  rc=$?"
echo "[$(date +%H:%M:%S)] exhaustive_matcher"
$C exhaustive_matcher --database_path $W/db.db --FeatureMatching.use_gpu 1 > $W/em.log 2>&1; echo "  rc=$?"
echo "[$(date +%H:%M:%S)] point_triangulator"
mkdir -p $W/sparse
$C point_triangulator --database_path $W/db.db --image_path $W/images \
   --input_path $W/sparse_in --output_path $W/sparse > $W/pt.log 2>&1; echo "  rc=$?"
ls -la $W/sparse/points3D.bin | awk '{printf "  points3D %.1f MB\n", $5/1048576}'
echo "[$(date +%H:%M:%S)] image_undistorter (official dense workspace)"
$C image_undistorter --image_path $W/images --input_path $W/sparse --output_path $W/dense \
   --output_type COLMAP --max_image_size 2000 > $W/iu.log 2>&1; echo "  rc=$?"
ls $W/dense | tr '\n' ' '; echo
echo "[$(date +%H:%M:%S)] FRONT_DONE"
