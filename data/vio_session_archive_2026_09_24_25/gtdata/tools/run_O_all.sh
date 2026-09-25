#!/bin/bash
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata
for s in V1_01_easy V1_02_medium V1_03_difficult; do
  OUT=$W/runs/euroc/$s.O.tum
  $W/tools/locked.sh $W/work/build-O/pw_euroc_runner_stream $W/cfg/slam_O.yaml $W/xrslam-wt-O/configs/euroc_sensor.yaml \
     euroc://$HOME/Developer/euroc/$s/mav0 $OUT --pace 1 --camera-out $W/runs/euroc/$s.O.cam.tum > $OUT.log 2>&1
  echo "[euroc $s/O] rc=$? poses=$(wc -l < $OUT)"
done
cd $W/work
for s in A6 B0 B3 B7; do /opt/homebrew/bin/python3.11 $W/tools/zju_run.py $s O > $W/work/zju_${s}_O.out 2>&1; grep -E "rc=|STOP|Error" $W/work/zju_${s}_O.out; done
echo ALL_O_DONE
