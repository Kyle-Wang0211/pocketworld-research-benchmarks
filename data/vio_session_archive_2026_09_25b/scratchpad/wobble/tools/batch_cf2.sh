#!/bin/bash
# 第二批:全部带 --log(可取后端 latest/kf_final)。
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble
C=$W/cfg; T=$W/tools
for sc in 13f5 6d18 7353 fb5d; do
  $T/run.sh ${sc}_offiphone_log_r1 $sc --log --slam $C/slam_offiphone_4beb1a9.yaml
  $T/run.sh ${sc}_td6_log_r1 $sc --log --td-extra-ms 6
  $T/run.sh ${sc}_td-4_log_r1 $sc --log --td-extra-ms -4
  $T/run.sh ${sc}_td4_log_r1 $sc --log --td-extra-ms 4
  $T/run.sh ${sc}_win10_log_r1 $sc --log --slam $C/slam_win10.yaml
done
$T/run.sh 13f5_offiphone_log_r2 13f5 --log --slam $C/slam_offiphone_4beb1a9.yaml
$T/run.sh 7353_offiphone_log_r2 7353 --log --slam $C/slam_offiphone_4beb1a9.yaml
echo BATCH_CF2_DONE
