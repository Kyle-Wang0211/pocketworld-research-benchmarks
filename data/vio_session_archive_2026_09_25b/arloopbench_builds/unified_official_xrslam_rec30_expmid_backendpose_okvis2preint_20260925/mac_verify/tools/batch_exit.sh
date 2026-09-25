#!/bin/bash
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
for sc in 13f5 6d18 7353; do
  $P/tools/run.sh ${sc}_okvis_state_nothr_p0 $sc okvis_state_nothr --pace 0 | head -1
  $P/tools/run.sh ${sc}_okvis_state_oldabi_nothr_p0 $sc okvis_state_oldabi_nothr --pace 0 | head -1
done
echo BATCH_EXIT_DONE
