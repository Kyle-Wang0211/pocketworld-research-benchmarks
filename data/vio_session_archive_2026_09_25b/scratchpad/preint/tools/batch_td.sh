#!/bin/bash
# 诊断(不改 td 规则):新积分器上把相机时间戳整体挪 −5 / −2.5 ms,看回退是不是时序配合造成的
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
until grep -q BATCH_DIAG_DONE $P/runs/batch_okvis.out 2>/dev/null; do sleep 5; done
for sc in 13f5 6d18 7353; do
  $P/tools/run.sh ${sc}_okvis_nothr_tdm5 $sc okvis_nothr --td-extra-ms -5
  $P/tools/run.sh ${sc}_okvis_nothr_tdm25 $sc okvis_nothr --td-extra-ms -2.5
done
echo BATCH_TD_DONE
