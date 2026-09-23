#!/bin/bash
# takeover batch (09-23): identical invocation per arm via run_arm_diag.sh; frees session.db after each run.
B=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sfmB
for job in "S_prod74 A" "S_prod74 Xhost" "S_prod74 Xdev640sweep" "S_deb74 A" "S_deb74 Xhost"; do
  set -- $job
  echo "[$(date +%T)] df=$(df -h ~ | tail -1 | awk '{print $4}') start $1 $2"
  bash $B/tools/run_arm_diag.sh $1 $2 || { echo "stopped at $1 $2"; break; }
  rm -f $B/runs/diag_$1_$2/session.db $B/runs/diag_$1_$2/session.db-shm $B/runs/diag_$1_$2/session.db-wal
  rm -rf $B/runs/diag_$1_$2/live/live_reg*
done
echo "[$(date +%T)] BATCH DONE df=$(df -h ~ | tail -1 | awk '{print $4}')"
