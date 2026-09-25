#!/bin/bash
# batch_as.sh —— 加计前移轮喂核:前移 16 / 21 ms(td Δ=−6 ms,扫参按后端定稿抖动判据选出)。
# e 组 × {F,X}{16,21},p 组 × {F,B}{16,21};3 场 × 3 相位 × 5 次,按 重复→场→相位→臂 交错。ARKit 沿用上一轮 AN / 第一轮 A。
O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm
for r in 1 2 3 4 5; do for s in 13f5 6d18 7353; do for p in 0 1 2; do
  for a in F16 X16 F21 X21; do $O/tools/run_arm.sh ${s}_e${p}_${a} $r || { echo "停止于 ${s}_e${p}_${a} r$r"; exit 1; }; done
  for a in F16 B16 F21 B21; do $O/tools/run_arm.sh ${s}_p${p}_${a} $r || { echo "停止于 ${s}_p${p}_${a} r$r"; exit 1; }; done
done; done; done
echo "加计前移批完成 $(date +%T)"
