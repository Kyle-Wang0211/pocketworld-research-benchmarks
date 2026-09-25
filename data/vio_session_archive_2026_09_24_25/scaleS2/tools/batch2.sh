#!/bin/bash
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
S=$SP/scaleS2; C=$S/cfg; A=$S/tools/arm.sh; M=$S/tools/arm_M.sh
until grep -q BATCH1_DONE $S/batch1.log; do sleep 10; done
R=$HOME/Developer/viobench-recordings
REF6=$R/run-6e2d4b99-896b-4372-ae47-ac0b4679cf18/arkit_poses.tum
D60=$R/_euroc_6e2d4b99_640; D30=$S/data/6e2d_640_30
$M 6e2d_M_B0 $C/slam_B.yaml $C/dev_B640_k0_td8.yaml $D60 $REF6
$M 6e2d_M_Kofficial $C/slam_B.yaml $C/dev_O_td8.yaml $D60 $REF6
$A 6e2d_B+IOS+Kofficial ios $C/slam_B.yaml $C/dev_O_td8.yaml $D60 $REF6
$M 6e2d_M_P0 $C/slam_P.yaml $C/dev_P_6e2d.yaml $D30 $REF6
$M 6e2d_M_slamO_60 $C/slam_O.yaml $C/dev_B640_k0_td8.yaml $D60 $REF6
$A 6e2d_B+IOS+slamO ios $C/slam_O.yaml $C/dev_B640_k0_td8.yaml $D60 $REF6
for r in 5966aec0-cbf1-4abc-af0e-c1fc559da44c 4ad6e500-ff59-4e67-9bb5-25fb2efe2faa; do
  s=${r:0:4}; REF=$R/run-$r/arkit_poses.tum; E60=$SP/xr_shared/euroc640_${r:0:8}; E30=$S/data/${s}_640_30
  $A ${s}_B0 gen $C/slam_B.yaml $C/dev_B640_${s}_td8.yaml $E60 $REF
  $A ${s}_B+IOS ios $C/slam_B.yaml $C/dev_B640_${s}_td8.yaml $E60 $REF
  $M ${s}_M_B0 $C/slam_B.yaml $C/dev_B640_${s}_td8.yaml $E60 $REF
  $A ${s}_B+Kofficial gen $C/slam_B.yaml $C/dev_O_td8.yaml $E60 $REF
  $A ${s}_B+IOS+Kofficial ios $C/slam_B.yaml $C/dev_O_td8.yaml $E60 $REF
  $A ${s}_B+30Hz gen $C/slam_B.yaml $C/dev_B640_${s}_td8.yaml $E30 $REF
  $A ${s}_B+slamO gen $C/slam_O.yaml $C/dev_B640_${s}_td8.yaml $E60 $REF
  $A ${s}_P0 gen $C/slam_P.yaml $C/dev_P_${s}.yaml $E30 $REF
  $A ${s}_P+IOS ios $C/slam_P.yaml $C/dev_P_${s}.yaml $E30 $REF
  $A ${s}_P+Kofficial gen $C/slam_P.yaml $C/dev_O.yaml $E30 $REF
  $A ${s}_O-thr ios_fm $C/slam_O.yaml $C/dev_O.yaml $E30 $REF
done
echo BATCH2_DONE
