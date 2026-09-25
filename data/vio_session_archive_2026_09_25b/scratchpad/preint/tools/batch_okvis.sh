#!/bin/bash
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
until grep -q BATCH_BASE_DONE $P/runs/batch_base.out 2>/dev/null; do sleep 5; done
for sc in 13f5 6d18 7353; do
  $P/tools/run.sh ${sc}_okvis_nothr_r1 $sc okvis_nothr
  $P/tools/run.sh ${sc}_okvis_nothr_r2 $sc okvis_nothr
  $P/tools/run.sh ${sc}_okvis_thr_r1 $sc okvis_thr
done
echo BATCH_OKVIS_DONE
for sc in 13f5 6d18 7353; do
  $P/tools/run.sh ${sc}_okvis_nothr_qark $sc okvis_nothr --dev $P/cfg/dev_${sc}_qark.yaml
  $P/tools/run.sh ${sc}_okvis_nothr_win10 $sc okvis_nothr --slam $P/cfg/slam_win10.yaml
done
echo BATCH_DIAG_DONE
