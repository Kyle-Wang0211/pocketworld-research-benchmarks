#!/bin/bash
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble
T=$W/tools
for sc in 13f5 6d18 7353; do
  for td in -4 2 4 6; do
    [ -f $W/runs/${sc}_td${td}_log_r1.jsonl ] && [ -s $W/runs/${sc}_td${td}_log_r1.cam.tum ] || $T/run.sh ${sc}_td${td}_log_r1 $sc --log --td-extra-ms $td
  done
done
echo BATCH_TD_DONE
