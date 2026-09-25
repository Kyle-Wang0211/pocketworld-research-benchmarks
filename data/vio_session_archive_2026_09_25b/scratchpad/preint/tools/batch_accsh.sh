#!/bin/bash
# 诊断:加计时间戳整体平移 −16 ms(输入端,与 td 同性质;引擎不动),两个引擎各扫 Δ
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
until grep -q BATCH_HOLD_DONE $P/runs/batch_hold.out 2>/dev/null; do sleep 5; done
$P/tools/run.sh 13f5_okvis_as0_check 13f5 okvis_as_nothr --pace 0 --acc-shift-ms 0 | head -1
for d in -5 0 -3 -7 -1 1 -4 -6 -2 2 -8; do for sc in 13f5 6d18 7353; do for e in base okvis; do
  n=$( [ $d -lt 0 ] && echo m${d#-} || echo p$d )
  $P/tools/run.sh ${sc}_${e}_as16_sw$n $sc ${e}_as_nothr --pace 0 --acc-shift-ms -16 --td-extra-ms $d | head -1
done; done; done
echo BATCH_ACCSH_DONE
