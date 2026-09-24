#!/bin/bash
# kill ONLY my own diag jobs if available memory < 8 GB (patterns match only scripts/files in /root/tsdf_improve/diag)
cd /root/tsdf_improve/diag
while pgrep -f "run_global.sh|run_detail.sh" >/dev/null; do
  a=$(free -g | awk '/Mem:/{print $7}')
  if [ "$a" -lt 8 ]; then
    echo "$(date) avail ${a}G < 8G -> killing my jobs" >> memguard.log
    pkill -f "run_global.sh|run_detail.sh"; pkill -f "global_tsdf\.py|to_av\.py|l2control\.py|_AV\.ply|detail_tsdf\.py|detail_metric\.py"
  fi
  echo "$(date +%T) avail ${a}G" >> memguard.log
  sleep 15
done
