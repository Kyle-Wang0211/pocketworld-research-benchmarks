#!/bin/bash
# 零效应扰动臂:测指标本身对微小扰动的敏感度(噪声底)
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble
T=$W/tools
for sc in 13f5 6d18 7353; do
  $T/run.sh ${sc}_nullp03_r1 $sc --td-extra-ms 0.3
  $T/run.sh ${sc}_nullm03_r1 $sc --td-extra-ms -0.3
  $T/run.sh ${sc}_nullfx_r1 $sc --k-scale 0 1e12 1.001
done
echo BATCH_CF3_DONE
