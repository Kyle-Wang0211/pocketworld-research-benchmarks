#!/bin/bash
# batch1: official unchanged (O) and pixel-scaled (S) at 960/1280/1920, 3 scenes, pace 1, r1
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/xrhires
A=$W/tools/arm.sh; C=$W/cfg
for sc in 4ad6 5966 6e2d; do
  for res in 960 1280 1920; do
    [ "$sc/$res" = "4ad6/1920" ] || $A ${sc}_${res}_O_p1_r1 $C/slam_O.yaml $C/dev_${sc}_${res}.yaml $sc $res 1 -
  done
  $A ${sc}_960_S_p1_r1  $C/slam_S1p5.yaml $C/dev_${sc}_960_n.yaml  $sc 960  1 "PW_PX_SCALE=1.5 PW_LK_EXTRA_LEVELS=1"
  $A ${sc}_1280_S_p1_r1 $C/slam_S2.yaml   $C/dev_${sc}_1280_n.yaml $sc 1280 1 "PW_PX_SCALE=2 PW_LK_EXTRA_LEVELS=1"
  $A ${sc}_1920_S_p1_r1 $C/slam_S3.yaml   $C/dev_${sc}_1920_n.yaml $sc 1920 1 "PW_PX_SCALE=3 PW_LK_EXTRA_LEVELS=2"
done
echo BATCH1_DONE
