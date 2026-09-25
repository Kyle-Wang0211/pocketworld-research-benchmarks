#!/bin/bash
# 反事实第一批:每场 base 之外的 11 个臂(各 1 次;确定性已由 base r1/r2 逐位相同证明,关键臂再补重复)
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble
C=$W/cfg; T=$W/tools
$T/run.sh fb5d_base_r1 fb5d
$T/run.sh fb5d_base_r2 fb5d
$T/run.sh fb5d_log_r1 fb5d --log
kc() { case $1 in 13f5) echo "1348.2379 962.7236 719.8389";; 6d18) echo "1351.0266 963.7433 720.1178";; 7353) echo "1353.2050 962.5877 720.1509";; fb5d) echo "1383.0764 963.2427 719.9141";; esac; }
for sc in 13f5 6d18 7353 fb5d; do
  for td in -4 -2 2 4; do $T/run.sh ${sc}_td${td}_r1 $sc --td-extra-ms $td; done
  $T/run.sh ${sc}_kconst_r1 $sc --k-const $(kc $sc)
  $T/run.sh ${sc}_fx099_r1 $sc --k-scale 0 1e12 0.99
  $T/run.sh ${sc}_fx101_r1 $sc --k-scale 0 1e12 1.01
  $T/run.sh ${sc}_qark_r1 $sc --dev $C/dev_${sc}_qark.yaml
  $T/run.sh ${sc}_park_r1 $sc --dev $C/dev_${sc}_park.yaml
  $T/run.sh ${sc}_ext_r1 $sc --dev $C/dev_${sc}_ext.yaml
  $T/run.sh ${sc}_win10_r1 $sc --slam $C/slam_win10.yaml
done
echo BATCH_CF1_DONE
