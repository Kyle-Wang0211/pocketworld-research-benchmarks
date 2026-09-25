#!/bin/bash
export PYTHONDONTWRITEBYTECODE=1
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
LR=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler/lidar_ruler.py
R=/Users/kaidongwang/Developer/viobench-recordings
for p in "13f5 run-13f53d2f-5935-4b1a-a499-4dc8367ea935" "6d18 run-6d187dff-403a-4882-b692-7bdc6c3cfa2a" "7353 run-73538ad6-8418-4eaf-8b75-a63c9d32af46"; do
  set -- $p; sc=$1; O=$P/ruler/out2_$sc; mkdir -p $O
  nice -n 10 /usr/bin/python3 $LR --recording $R/$2/ruler_subset --arkit \
    --camera new_m5_final=$P/ruler/${sc}_all_m5_final.tum --camera as16new_m4_final=$P/ruler/${sc}_as16new_m4_final.tum \
    --camera old_p0_final=$P/ruler/${sc}_none_p0_final.tum --pairs 90 --out $O > $O/stdout.txt 2>&1
  echo "done $sc rc=$?"
done
echo RULER2_DONE
