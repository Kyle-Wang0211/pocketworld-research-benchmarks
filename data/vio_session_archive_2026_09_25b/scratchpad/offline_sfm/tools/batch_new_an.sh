#!/bin/bash
# batch_new_an.sh —— 补跑:新照片 e 组的 ARKit 臂(AN),3 场 × 3 相位 × 5 次。
O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm
for r in 1 2 3 4 5; do for s in 13f5 6d18 7353; do for p in 0 1 2; do
  $O/tools/run_arm.sh ${s}_e${p}_AN $r || { echo "停止于 ${s}_e${p}_AN r$r"; exit 1; }
done; done; done
echo "AN 补跑完成 $(date +%T)"
