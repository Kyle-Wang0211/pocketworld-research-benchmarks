#!/bin/bash
export PYTHONDONTWRITEBYTECODE=1
for p in "fb5d fb5d_log_r1 run-fb5d3a8f-6e31-463e-989d-bd73bb3a2def" "13f5 13f5_log_r1 run-13f53d2f-5935-4b1a-a499-4dc8367ea935" "6d18 6d18_log_r1 run-6d187dff-403a-4882-b692-7bdc6c3cfa2a" "7353 7353_log_r1 run-73538ad6-8418-4eaf-8b75-a63c9d32af46"; do
  set -- $p
  O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/stats/ruler_$1; mkdir -p $O
  /usr/bin/python3 /Users/kaidongwang/.config/superpowers/worktrees/pocketworld/bench-rec30-ruler-exact-20260924/tool/bench/lidar_ruler/lidar_ruler.py --recording /Users/kaidongwang/Developer/viobench-recordings/$3/ruler_subset --arkit --camera api=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/stats/tum_$2_api.tum --camera latest=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/stats/tum_$2_latest.tum --camera kf=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/wobble/stats/tum_$2_kf.tum --pairs 90 --out $O > $O/stdout.txt 2>&1
  echo "done $1 rc=$?"
done
echo RULER_DONE
