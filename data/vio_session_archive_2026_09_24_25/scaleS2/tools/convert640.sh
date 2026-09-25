#!/bin/bash
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad
R=$HOME/Developer/viobench-recordings
until mkdir $SP/xr_shared.lock 2>/dev/null; do sleep 10; done
trap 'rmdir $SP/xr_shared.lock' EXIT
mkdir -p $SP/xr_shared
for id in 5966aec0-cbf1-4abc-af0e-c1fc559da44c 4ad6e500-ff59-4e67-9bb5-25fb2efe2faa; do
  s=${id:0:8}; out=$SP/xr_shared/euroc640_$s
  [ -f $out/imu0/data.csv ] && { echo "exists $out"; continue; }
  free=$(df -k /private/tmp | tail -1 | awk '{print $4}')
  [ $free -lt 3400000 ] && { echo "LOW DISK ($free KB), skip $s"; continue; }
  /usr/bin/python3 $HOME/Developer/arloopbench/tools/pwvi_to_euroc.py $R/run-$id $out --downscale 3 --intrinsics-csv $SP/xr_shared/k640_$s.csv 2>&1 | tail -4
  echo "S2 made $out (640x480 box/3 of run-$id, pwvi_to_euroc.py --downscale 3)" > $out/README.S2
done
ln -sfn $R/_euroc_6e2d4b99_640 $SP/xr_shared/euroc640_6e2d4b99
du -sh $SP/xr_shared/* ; df -h /private/tmp | tail -1
