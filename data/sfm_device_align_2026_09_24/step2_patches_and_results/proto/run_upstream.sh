#!/bin/bash
# Upstream COLMAP (homebrew 4.1.1 CLI) on a COPY of the phone's database. Arms:
#   U0  colmap mapper                         (upstream incremental SfM, no priors)
#   U1  colmap pose_prior_mapper σ=0.04 m     (exe/sfm.cc RunPosePriorMapper, overwrite_priors_covariance, squared loss)
#   U2  colmap pose_prior_mapper σ=0.04 m + use_robust_loss_on_prior_position (Cauchy, scale 7.815 default)
# Intrinsics fixed like the core (ba_refine_* = 0; per-image PINHOLE K from the phone). Fixed seed. Sequential.
set -uo pipefail
P=$(cd "$(dirname "$0")" && pwd); CAP=$1; shift; ARMS=${*:-U0 U1 U2}; D=$P/$CAP
avail_kb=$(df -k ~ | tail -1 | awk '{print $4}'); [ "$avail_kb" -lt $((1536*1024)) ] && { echo "STOP disk"; exit 90; }
COMMON="--database_path $D/db.db --image_path $D/noimages --Mapper.ba_refine_focal_length 0 --Mapper.ba_refine_principal_point 0 --Mapper.ba_refine_extra_params 0 --Mapper.random_seed 1 --Mapper.num_threads 6 --Mapper.multiple_models 0"
for A in $ARMS; do
  rm -rf $D/$A; mkdir -p $D/$A
  case $A in
    U0) CMD="colmap mapper $COMMON --output_path $D/$A";;
    U1) CMD="colmap pose_prior_mapper $COMMON --output_path $D/$A --overwrite_priors_covariance 1 --prior_position_std_x 0.04 --prior_position_std_y 0.04 --prior_position_std_z 0.04";;
    U2) CMD="colmap pose_prior_mapper $COMMON --output_path $D/$A --overwrite_priors_covariance 1 --prior_position_std_x 0.04 --prior_position_std_y 0.04 --prior_position_std_z 0.04 --use_robust_loss_on_prior_position 1";;
  esac
  cp $D/db.db $D/$A/db_work.db
  CMD=${CMD//$D\/db.db/$D/$A/db_work.db}
  /usr/bin/time -l $CMD > $D/$A/log.txt 2>&1; rc=$?
  rm -f $D/$A/db_work.db
  M=$(ls -d $D/$A/*/ 2>/dev/null | head -1)
  [ -n "$M" ] && colmap model_converter --input_path $M --output_path $D/$A --output_type TXT > /dev/null 2>&1
  [ -n "$M" ] && colmap model_analyzer --path $M > $D/$A/analyzer.txt 2>&1
  echo "$CAP $A rc=$rc model=$M $(grep -E 'Registered images|Points|Mean reprojection|Mean track length' $D/$A/analyzer.txt 2>/dev/null | sed 's/.*\] //' | tr '\n' ' ')"
done
