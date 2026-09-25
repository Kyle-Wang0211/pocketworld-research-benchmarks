#!/bin/bash
RA=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/ruler_audit
WT=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/bench-lidar-ruler-v2-20260925/tool/bench/lidar_ruler
sc=$1; run=$2; R=/Users/kaidongwang/Developer/viobench-recordings/$run; T=$RA/tums/$sc
C=""; for cfg in "old:scnone_ap0_swp0" "new_acc16:scall_am16_swm4" "new_acc0:scall_ap0_swm4"; do n=${cfg%%:*}; c=${cfg#*:}
  C="$C --camera ${n}_front=${T}_${c}_front.tum --camera ${n}_final=${T}_${c}_final.tum"; done
PYTHONDONTWRITEBYTECODE=1 nice -n 10 /usr/bin/python3 $WT/lidar_ruler.py --recording $R --depth-dir $R/ruler_subset --arkit $C --out $RA/v2runs/$sc > $RA/v2runs/$sc.log 2>&1
echo "rc=$? $sc" >> $RA/v2runs/$sc.log
