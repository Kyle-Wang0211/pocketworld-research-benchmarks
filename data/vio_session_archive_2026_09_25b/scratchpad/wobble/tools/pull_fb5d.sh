#!/bin/bash
DEV=1B290474-D354-5B4C-AAB0-0805AC5DC832
D=$HOME/Developer/viobench-recordings/run-fb5d3a8f-6e31-463e-989d-bd73bb3a2def
avail=$(df -k ~ | awk 'NR==2{print $4}')
[ $avail -lt 8000000 ] && { echo "磁盘不足 $avail KB"; exit 3; }
xcrun devicectl device copy from --device $DEV --domain-type appDataContainer --domain-identifier com.kyle.arloopbench \
  --source Documents/replay_recordings/run-fb5d3a8f-6e31-463e-989d-bd73bb3a2def/frames.bin --destination $D/frames.bin 2>&1 | tail -2
for f in imu.csv intrinsics.jsonl arkit_poses.tum; do [ -e $D/$f ] || ln $D/ruler_subset/$f $D/$f; done
ls -la $D/frames.bin; df -h ~ | tail -1
echo PULL_FB5D_DONE
