#!/bin/bash
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
S=$SP/scaleS2; C=$S/cfg; A=$S/tools/arm.sh; M=$S/tools/arm_M.sh
until grep -q BATCH4_DONE $S/batch4.log; do sleep 20; done
R=$HOME/Developer/viobench-recordings; REF=$R/run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa/arkit_poses.tum
H=$SP/xr_shared/euroc1920_4ad6e500; L=$SP/xr_shared/euroc640_4ad6e500
for td in 0.0126 0.004 0.0; do
  $A 4ad6_R1920_td$td gen $C/slam_B.yaml $C/dev_B1920_4ad6_td$td.yaml $H $REF
  $A 4ad6_R640_td$td gen $C/slam_B.yaml $C/dev_B640_4ad6_td$td.yaml $L $REF
done
$A 4ad6_R1920_td0.0126_IOS ios $C/slam_B.yaml $C/dev_B1920_4ad6_td0.0126.yaml $H $REF
$M 4ad6_R1920_td0.0126_M $C/slam_B.yaml $C/dev_B1920_4ad6_td0.0126.yaml $H $REF
echo BATCH5_DONE
