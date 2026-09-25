#!/bin/bash
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
S=$SP/scaleS2; C=$S/cfg; A=$S/tools/arm.sh
until grep -q BATCH2B_DONE $S/batch2b.log; do sleep 10; done
R=$HOME/Developer/viobench-recordings
REF6=$R/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum
D60=$R/_euroc_6e2d4b99_640; D30=$S/data/6e2d_640_30
# divergence anatomy (gen = XRSLAM_IOS off, THREADING off)
$A 6e2d_div_Oexp60 gen $C/slam_Oexp.yaml $C/dev_B640_k0_td8.yaml $D60 $REF6
$A 6e2d_div_slamO30 gen $C/slam_O.yaml $C/dev_B640_k0_td8.yaml $D30 $REF6
for f in $C/slam_Oexp__keepB-*.yaml; do n=$(basename $f .yaml); $A 6e2d_div_${n#slam_Oexp__} gen $f $C/dev_B640_k0_td8.yaml $D60 $REF6; done
# threaded arms, paced 1x real time
for i in 1 2 3; do $A 6e2d_O_full_r$i official $C/slam_O.yaml $C/dev_O.yaml $D30 $REF6 --pace 1; done
for i in 1 2; do $A 6e2d_P+THR_r$i off_thr $C/slam_P.yaml $C/dev_P_6e2d.yaml $D30 $REF6 --pace 1; done
for r in 5966aec0-cbf1-4abc-af0e-c1fc559da44c 4ad6e500-ff59-4e67-9bb5-25fb2efe2faa; do
  s=${r:0:4}; REF=$R/run-$r/arkit_poses.tum; E30=$S/data/${s}_640_30
  for i in 1 2; do $A ${s}_O_full_r$i official $C/slam_O.yaml $C/dev_O.yaml $E30 $REF --pace 1; done
done
echo BATCH3_DONE
