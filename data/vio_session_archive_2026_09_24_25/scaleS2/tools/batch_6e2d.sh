#!/bin/bash
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/scaleS2
C=$S/cfg; A=$S/tools/arm.sh
REF=$HOME/Developer/viobench-recordings/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum
D60=$HOME/Developer/viobench-recordings/_euroc_6e2d4b99_640; D30=$S/data/6e2d_640_30
# ---- B family (bench replay config, 60 Hz) : single differences toward official
$A 6e2d_B0 gen $C/slam_B.yaml $C/dev_B640_k0_td8.yaml $D60 $REF
for k in sliding_window-size sliding_window-tracker_frequent rotation-misalignment_threshold initializer-min_triangulation feature_tracker-max_frames feature_tracker-max_keypoint_detection solver win5tf3; do
  $A 6e2d_B+$k gen $C/slam_B__$k.yaml $C/dev_B640_k0_td8.yaml $D60 $REF
done
$A 6e2d_B+slamO gen $C/slam_O.yaml $C/dev_B640_k0_td8.yaml $D60 $REF
$A 6e2d_B+30Hz gen $C/slam_B.yaml $C/dev_B640_k0_td8.yaml $D30 $REF
$A 6e2d_B+td0 gen $C/slam_B.yaml $C/dev_B640_k0_td0.yaml $D60 $REF
$A 6e2d_B+Kofficial gen $C/slam_B.yaml $C/dev_O_td8.yaml $D60 $REF
$A 6e2d_B+IOS ios $C/slam_B.yaml $C/dev_B640_k0_td8.yaml $D60 $REF
$A 6e2d_B+fastmath gen_fm $C/slam_B.yaml $C/dev_B640_k0_td8.yaml $D60 $REF
# ---- P family (production emulation: slam_P + ARKit K0 scaledTo + td0 + 30 Hz)
$A 6e2d_P0 gen $C/slam_P.yaml $C/dev_P_6e2d.yaml $D30 $REF
$A 6e2d_P+IOS ios $C/slam_P.yaml $C/dev_P_6e2d.yaml $D30 $REF
$A 6e2d_P+fastmath gen_fm $C/slam_P.yaml $C/dev_P_6e2d.yaml $D30 $REF
$A 6e2d_P+Kofficial gen $C/slam_P.yaml $C/dev_O.yaml $D30 $REF
$A 6e2d_P+slamO gen $C/slam_O.yaml $C/dev_P_6e2d.yaml $D30 $REF
# ---- official minus threading (deterministic), and official minus IOS
$A 6e2d_O-thr ios_fm $C/slam_O.yaml $C/dev_O.yaml $D30 $REF
$A 6e2d_O-ios gen_fm $C/slam_O.yaml $C/dev_O.yaml $D30 $REF
echo BATCH1_DONE
