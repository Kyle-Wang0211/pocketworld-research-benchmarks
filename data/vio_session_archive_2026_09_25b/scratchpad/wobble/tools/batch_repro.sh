#!/bin/bash
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble
for sc in 13f5 6d18; do
  $W/tools/run.sh ${sc}_base_r1 $sc
  $W/tools/run.sh ${sc}_base_r2 $sc
  $W/tools/run.sh ${sc}_log_r1 $sc --log
done
# 7353 等拉取完成
until grep -q "run-73538ad6.*frames.bin" $W/logs/pull.log && [ "$(stat -f %z $HOME/Developer/viobench-recordings/run-73538ad6-8418-4eaf-8b75-a63c9d32af46/frames.bin 2>/dev/null)" -gt 2400000000 ] && grep -q "Filesystem" $W/logs/pull.log; do sleep 10; done
for sc in 7353; do
  $W/tools/run.sh ${sc}_base_r1 $sc
  $W/tools/run.sh ${sc}_base_r2 $sc
  $W/tools/run.sh ${sc}_log_r1 $sc --log
done
$W/tools/run.sh fb5d_base_r1 fb5d
$W/tools/run.sh fb5d_log_r1 fb5d --log
echo BATCH_DONE
