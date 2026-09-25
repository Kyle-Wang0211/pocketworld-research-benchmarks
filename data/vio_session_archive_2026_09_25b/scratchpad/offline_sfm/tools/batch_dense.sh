#!/bin/bash
# batch_dense.sh —— 补充批:0.25 s 密节奏(每场 115 张)× 4 臂 × 3 次,主批结束后再跑。
O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm
until grep -q "主批完成\|停止于" $O/batch_main.log 2>/dev/null; do sleep 10; done
grep -q "停止于" $O/batch_main.log && { echo "主批中途停止,补充批不跑"; exit 1; }
for r in 1 2 3; do for s in 13f5 6d18 7353; do for a in A F B1 B2; do
  $O/tools/run_arm.sh ${s}_q0_${a} $r || { echo "停止于 ${s}_q0_${a} r$r"; exit 1; }
done; done; done
echo "补充批完成 $(date +%T)"
