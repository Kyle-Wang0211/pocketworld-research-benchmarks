#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/dip13f
until grep -q BATCH2_DONE runs/batch2.out; do sleep 5; done
for r in 1 2; do
  for s in 6e2d 5966 4ad6; do
    ./tools/run2.sh ${s}_td0_r$r $s --log
    ./tools/run2.sh ${s}_td8_r$r $s --log --dev cfg/dev_${s}_td8.yaml
  done
  ./tools/run2.sh 4ad6_expmid_r$r 4ad6 --log --dev cfg/dev_4ad6_td2p65.yaml --exposure-half
done
echo BATCH3_DONE
