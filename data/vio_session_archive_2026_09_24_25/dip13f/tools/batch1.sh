#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/dip13f
T0=254666.645033333
a() { /usr/bin/python3 -c "print('%.6f'%($T0+$1))"; }
for r in 1 2; do
./tools/run.sh td8_r$r inst 13f5 --log --dev cfg/dev_td8.yaml
./tools/run.sh tdm8_r$r inst 13f5 --log --dev cfg/dev_td-8.yaml
./tools/run.sh td15_r$r inst 13f5 --log --dev cfg/dev_td15.yaml
./tools/run.sh kconst_r$r inst 13f5 --log --k-const 1348.24377 962.72925 719.84436
./tools/run.sh kholdhi_r$r inst 13f5 --log --k-hold $(a 22.5) $(a 26.8)
./tools/run.sh kholdmid_r$r inst 13f5 --log --k-hold $(a 15.0) $(a 19.5)
./tools/run.sh rpe6_r$r inst 13f5 --log --slam cfg/slam_rpe6.yaml
./tools/run.sh cova100_r$r inst 13f5 --log --dev cfg/dev_cova100.yaml
./tools/run.sh win10_r$r inst 13f5 --log --slam cfg/slam_win10it30.yaml
done
echo BATCH1_DONE
