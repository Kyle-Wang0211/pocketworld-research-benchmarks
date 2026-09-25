#!/bin/bash
# 只从台架容器复制文件(devicectl copy from),不装机、不启动 App。
DEV=1B290474-D354-5B4C-AAB0-0805AC5DC832
R=$HOME/Developer/viobench-recordings
for r in run-6d187dff-403a-4882-b692-7bdc6c3cfa2a run-73538ad6-8418-4eaf-8b75-a63c9d32af46; do
  D=$R/$r; mkdir -p $D
  for f in frames.pwvi camera_index.csv frames.bin; do
    avail=$(df -k ~ | awk 'NR==2{print $4}')
    if [ "$f" = frames.bin ] && [ $avail -lt 6000000 ]; then echo "磁盘不足 $avail KB,停止"; exit 3; fi
    echo "$(date +%T) pull $r/$f"
    xcrun devicectl device copy from --device $DEV --domain-type appDataContainer --domain-identifier com.kyle.arloopbench \
      --source Documents/replay_recordings/$r/$f --destination $D/$f 2>&1 | tail -2
  done
  # 其余文件与 ruler_subset 同名同大小 ⇒ 硬链接
  for f in arkit_poses.tum calibration.json config.json imu.csv input_manifest.json intrinsics.jsonl intrinsics_observed.json recorder_timing.json recording_manifest.json depth_meta.json; do
    [ -e $D/$f ] || ln $D/ruler_subset/$f $D/$f
  done
  ls -la $D
done
df -h ~
