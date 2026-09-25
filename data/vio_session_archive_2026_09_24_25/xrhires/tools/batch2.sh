#!/bin/bash
# batch2: repeats (r2), ablations at 1920, time-offset +-4 ms and rate-frac 0.8 perturbations, pace 0.25 check
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/xrhires
A=$W/tools/arm.sh; C=$W/cfg
E15="PW_PX_SCALE=1.5 PW_LK_EXTRA_LEVELS=1"; E2="PW_PX_SCALE=2 PW_LK_EXTRA_LEVELS=1"; E3="PW_PX_SCALE=3 PW_LK_EXTRA_LEVELS=2"
for sc in 4ad6 5966 6e2d; do
  # repeats
  $A ${sc}_640_O_p1_r2  $C/slam_O.yaml $C/dev_${sc}_640.yaml $sc 640 1 -
  for res in 960 1280 1920; do $A ${sc}_${res}_O_p1_r2 $C/slam_O.yaml $C/dev_${sc}_${res}.yaml $sc $res 1 -; done
  $A ${sc}_960_S_p1_r2  $C/slam_S1p5.yaml $C/dev_${sc}_960_n.yaml  $sc 960  1 "$E15"
  $A ${sc}_1280_S_p1_r2 $C/slam_S2.yaml   $C/dev_${sc}_1280_n.yaml $sc 1280 1 "$E2"
  $A ${sc}_1920_S_p1_r2 $C/slam_S3.yaml   $C/dev_${sc}_1920_n.yaml $sc 1920 1 "$E3"
  # ablations at 1920
  $A ${sc}_1920_A1noiseOnly_p1_r1 $C/slam_O.yaml  $C/dev_${sc}_1920_n.yaml $sc 1920 1 -
  $A ${sc}_1920_A2SnoNoise_p1_r1  $C/slam_S3.yaml $C/dev_${sc}_1920.yaml   $sc 1920 1 "$E3"
  $A ${sc}_1920_A3Sblock9_p1_r1   $C/slam_S3.yaml $C/dev_${sc}_1920_n.yaml $sc 1920 1 "$E3 PW_GFTT_BLOCK=9"
  $A ${sc}_1920_A4yamlOnly_p1_r1  $C/slam_S3.yaml $C/dev_${sc}_1920_n.yaml $sc 1920 1 -
done
for sc in 4ad6 5966 6e2d; do
  for td in 0.004 -0.004; do
    $A ${sc}_640_O_td${td}   $C/slam_O.yaml  $C/dev_${sc}_640_td${td}.yaml     $sc 640  1 -
    $A ${sc}_1280_S_td${td}  $C/slam_S2.yaml $C/dev_${sc}_1280_n_td${td}.yaml  $sc 1280 1 "$E2"
    $A ${sc}_1920_O_td${td}  $C/slam_O.yaml  $C/dev_${sc}_1920_td${td}.yaml    $sc 1920 1 -
    $A ${sc}_1920_S_td${td}  $C/slam_S3.yaml $C/dev_${sc}_1920_n_td${td}.yaml  $sc 1920 1 "$E3"
  done
  $A ${sc}_640_O_g08   $C/slam_O.yaml  $C/dev_${sc}_640.yaml     $sc 640  1 -    --rate-frac 0.8
  $A ${sc}_1280_S_g08  $C/slam_S2.yaml $C/dev_${sc}_1280_n.yaml  $sc 1280 1 "$E2" --rate-frac 0.8
  $A ${sc}_1920_O_g08  $C/slam_O.yaml  $C/dev_${sc}_1920.yaml    $sc 1920 1 -    --rate-frac 0.8
  $A ${sc}_1920_S_g08  $C/slam_S3.yaml $C/dev_${sc}_1920_n.yaml  $sc 1920 1 "$E3" --rate-frac 0.8
done
for sc in 4ad6 5966 6e2d; do
  $A ${sc}_1920_S_p025 $C/slam_S3.yaml $C/dev_${sc}_1920_n.yaml $sc 1920 0.25 "$E3"
  $A ${sc}_1920_O_p025 $C/slam_O.yaml  $C/dev_${sc}_1920.yaml   $sc 1920 0.25 -
done
echo BATCH2_DONE
