#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/dip13f
for r in 1 2; do
  ./tools/run2.sh fb5d_td0_r$r fb5d --log
  ./tools/run2.sh fb5d_td8_r$r fb5d --log --dev cfg/dev_fb5d_td8.yaml
  ./tools/run2.sh fb5d_expmid_r$r fb5d --log --dev cfg/dev_fb5d_td2p65.yaml --exposure-half
done
echo BATCH4_DONE
