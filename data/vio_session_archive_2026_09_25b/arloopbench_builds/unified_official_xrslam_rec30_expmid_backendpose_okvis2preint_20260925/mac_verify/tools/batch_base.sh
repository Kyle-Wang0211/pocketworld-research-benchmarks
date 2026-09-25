#!/bin/bash
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
for sc in 13f5 6d18 7353; do
  $P/tools/run.sh ${sc}_base_nothr_r1 $sc base_nothr
  $P/tools/run.sh ${sc}_base_nothr_r2 $sc base_nothr
  $P/tools/run.sh ${sc}_base_thr_r1 $sc base_thr
done
echo BATCH_BASE_DONE
