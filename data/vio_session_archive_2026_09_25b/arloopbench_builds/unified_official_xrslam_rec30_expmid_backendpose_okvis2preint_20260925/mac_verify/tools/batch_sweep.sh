#!/bin/bash
# td 扫描:t_feed = PTS + exposure/2 + c(c = 3 ms 不动)再加 Δ(--td-extra-ms),Δ = −10…+4 ms 每 1 ms 一档。
# 两个引擎(改前 base = 8ebac9a、改后 okvis = bdf9080),单线程,--pace 0(已验证与 1× 实时逐位相同)。
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
for d in -10 -9 -8 -7 -6 -5 -4 -3 -2 -1 0 1 2 3 4; do
  n=$( [ $d -lt 0 ] && echo m${d#-} || echo p$d )
  for sc in 13f5 6d18 7353; do
    for e in base okvis; do
      $P/tools/run.sh ${sc}_${e}_nothr_sw${n} $sc ${e}_nothr --td-extra-ms $d --pace 0 | head -1
    done
  done
  df -h ~ | tail -1 | awk '{print "disk", $4}'
done
echo BATCH_SWEEP_DONE
