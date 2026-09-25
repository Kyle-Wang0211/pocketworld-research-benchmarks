#!/bin/bash
# batch_as_sweep.sh —— 加计前移 16 / 21 ms × td −8 −6 −5 −4 −2 ms × 三场(−5 与上一轮同 td,用于单变量对比)。
O=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/offline_sfm
for as in -16 -21; do for td in -5 -8 -6 -4 -2; do for s in 13f5 6d18 7353; do
  $O/tools/run_as.sh ${s}_as${as#-}_td${td} $s $as $td || { echo "停止于 ${s} as$as td$td"; exit 1; }
done; done; done
echo "扫参完成 $(date +%T)"
