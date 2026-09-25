#!/bin/bash
# batch3: "N" = complete pixel normalisation (S + GFTT Harris blockSize x s) -- the arm that matched 640 on 4ad6/5966 (A3)
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/xrhires
A=$W/tools/arm.sh; C=$W/cfg
until grep -q ALL_DONE $W/logs/batch2b.log; do sleep 15; done
N15="PW_PX_SCALE=1.5 PW_LK_EXTRA_LEVELS=1 PW_GFTT_BLOCK=5"; N2="PW_PX_SCALE=2 PW_LK_EXTRA_LEVELS=1 PW_GFTT_BLOCK=6"; N3="PW_PX_SCALE=3 PW_LK_EXTRA_LEVELS=2 PW_GFTT_BLOCK=9"
for r in r1 r2; do for sc in 4ad6 5966 6e2d; do
  $A ${sc}_960_N_p1_$r  $C/slam_S1p5.yaml $C/dev_${sc}_960_n.yaml  $sc 960  1 "$N15"
  $A ${sc}_1280_N_p1_$r $C/slam_S2.yaml   $C/dev_${sc}_1280_n.yaml $sc 1280 1 "$N2"
  [ $r = r1 ] && [ $sc != 6e2d ] || $A ${sc}_1920_N_p1_$r $C/slam_S3.yaml $C/dev_${sc}_1920_n.yaml $sc 1920 1 "$N3"
done; done
for sc in 4ad6 5966 6e2d; do
  for td in 0.004 -0.004; do
    $A ${sc}_1920_N_td${td} $C/slam_S3.yaml $C/dev_${sc}_1920_n_td${td}.yaml $sc 1920 1 "$N3"
    $A ${sc}_1280_N_td${td} $C/slam_S2.yaml $C/dev_${sc}_1280_n_td${td}.yaml $sc 1280 1 "$N2"
  done
  $A ${sc}_1920_N_g08 $C/slam_S3.yaml $C/dev_${sc}_1920_n.yaml $sc 1920 1 "$N3" --rate-frac 0.8
  $A ${sc}_1280_N_g08 $C/slam_S2.yaml $C/dev_${sc}_1280_n.yaml $sc 1280 1 "$N2" --rate-frac 0.8
  $A ${sc}_1920_N_p025 $C/slam_S3.yaml $C/dev_${sc}_1920_n.yaml $sc 1920 0.25 "$N3"
done
echo BATCH3_DONE
