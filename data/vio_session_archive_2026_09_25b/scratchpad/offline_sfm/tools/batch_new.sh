#!/bin/bash
# batch_new.sh —— 新引擎轮:e 组(非后端帧)× A FN XN,p 组(后端帧)× FN BN;3 场 × 3 相位 × 5 次,按 重复→场→相位→臂 交错。
# e 组的 A 必须重跑(新照片组与上一轮有 1–2 帧不同);p 组照片与第一轮逐张相同,A / 旧 F / 旧 B2 沿用第一轮。
# 同名旧 e 组 A 运行目录先挪到 runs_prev_e_A/ 保留(上一轮结果不删)。
O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm
for r in 1 2 3 4 5; do for s in 13f5 6d18 7353; do for p in 0 1 2; do
  for a in A FN XN; do
    D=$O/runs/${s}_e${p}_${a}_r$r
    if [ "$a" = A ] && [ -d "$D" ] && [ ! -e "$O/runs_prev_e_A/${s}_e${p}_A_r$r" ]; then mkdir -p $O/runs_prev_e_A; mv "$D" $O/runs_prev_e_A/; fi
    $O/tools/run_arm.sh ${s}_e${p}_${a} $r || { echo "停止于 ${s}_e${p}_${a} r$r"; exit 1; }
  done
  for a in FN BN; do
    $O/tools/run_arm.sh ${s}_p${p}_${a} $r || { echo "停止于 ${s}_p${p}_${a} r$r"; exit 1; }
  done
done; done; done
echo "新引擎批完成 $(date +%T)"
