#!/bin/bash
# batch_main.sh —— 主批:3 场 × 3 相位 × 4 臂 × 5 次,按 重复→场→相位→臂 交错。
O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm
for r in 1 2 3 4 5; do for s in 13f5 6d18 7353; do for p in 0 1 2; do for a in A F B1 B2; do
  [ "$r" -le 2 ] && [ "$s$p$a" = "13f50A" ] && [ -f $O/runs/13f5_p0_A_r$r/metrics.json ] && continue
  $O/tools/run_arm.sh ${s}_p${p}_${a} $r || { echo "停止于 ${s}_p${p}_${a} r$r"; exit 1; }
done; done; done; done
echo "主批完成 $(date +%T)"
