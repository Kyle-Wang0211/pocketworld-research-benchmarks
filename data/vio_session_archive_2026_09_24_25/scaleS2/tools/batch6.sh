#!/bin/bash
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
S=$SP/scaleS2; C=$S/cfg; A=$S/tools/arm.sh
until grep -q BATCH5_DONE $S/batch5.log; do sleep 20; done
R=$HOME/Developer/viobench-recordings
REF6=$R/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum; REF4=$R/run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa/arkit_poses.tum
D60=$R/_euroc_6e2d4b99_640; D30=$S/data/6e2d_640_30; L=$SP/xr_shared/euroc640_4ad6e500
for p in fx1.001 fx0.999 cx+0.5; do
  $A 6e2d_NF_B_$p gen $C/slam_B.yaml $C/pert_6e2d_$p.yaml $D60 $REF6
  $A 4ad6_NF_B_$p gen $C/slam_B.yaml $C/pert_4ad6_$p.yaml $L $REF4
  $A 6e2d_NF_P_$p gen $C/slam_P.yaml $C/pert_P6e2d_$p.yaml $D30 $REF6
  $A 6e2d_NF_P+IOS_$p ios $C/slam_P.yaml $C/pert_P6e2d_$p.yaml $D30 $REF6
done
echo BATCH6_DONE
