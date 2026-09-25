#!/bin/bash
# td sweep + exposure-midpoint rule on 13f5 (2 repeats each)
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/dip13f
for r in 1 2; do
  for td in 2 4 6 10 12; do ./tools/run.sh td${td}_r$r inst 13f5 --log --dev cfg/dev_td$td.yaml; done
  ./tools/run.sh expmid_r$r inst 13f5 --log --dev cfg/dev_td2p65.yaml --exposure-half
done
echo BATCH2_DONE
