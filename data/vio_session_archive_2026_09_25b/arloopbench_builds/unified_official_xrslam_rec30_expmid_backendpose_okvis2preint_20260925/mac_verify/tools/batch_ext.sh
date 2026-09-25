#!/bin/bash
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
# 协方差诊断(只诊断):diagcov1 = 去掉 OKVIS2 的「姿态/位置/速度 × 零偏」交叉块;diagcov2 = 协方差整体换回 8ebac9a 算法
for d in -5 0; do n=$( [ $d -lt 0 ] && echo m${d#-} || echo p$d )
  for sc in 13f5 6d18 7353; do for v in diagcov1 diagcov2; do
    $P/tools/run.sh ${sc}_${v}_nothr_sw${n} $sc ${v}_nothr --td-extra-ms $d --pace 0 | head -1
  done; done
done
echo BATCH_DIAGCOV_DONE
# 扫描外延 Δ = +5…+8(改前 6d18 在 +4 仍未到底)
for d in 5 6 7 8; do for sc in 13f5 6d18 7353; do for e in base okvis; do
  $P/tools/run.sh ${sc}_${e}_nothr_swp$d $sc ${e}_nothr --td-extra-ms $d --pace 0 | head -1
done; done; done
echo BATCH_EXT_DONE
