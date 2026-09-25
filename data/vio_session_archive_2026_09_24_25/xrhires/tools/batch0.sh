#!/bin/bash
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/xrhires
A=$W/tools/arm.sh; C=$W/cfg
for sc in 5966 4ad6 6e2d; do $A ${sc}_640_O_p1_r1 $C/slam_O.yaml $C/dev_${sc}_640.yaml $sc 640 1 -; done
$A 4ad6_1920_O_p1_r1 $C/slam_O.yaml $C/dev_4ad6_1920.yaml 4ad6 1920 1 -
echo BATCH0_DONE
