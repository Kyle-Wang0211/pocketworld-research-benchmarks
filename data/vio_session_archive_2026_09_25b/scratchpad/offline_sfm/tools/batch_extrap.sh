#!/bin/bash
# batch_extrap.sh —— 外推轮:3 场 × 3 相位 × 4 臂(A F X2 X1)× 5 次,按 重复→场→相位→臂 交错。
O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm
for r in 1 2 3 4 5; do for s in 13f5 6d18 7353; do for p in 0 1 2; do for a in A F X2 X1; do
  $O/tools/run_arm.sh ${s}_e${p}_${a} $r || { echo "停止于 ${s}_e${p}_${a} r$r"; exit 1; }
done; done; done; done
echo "外推批完成 $(date +%T)"
