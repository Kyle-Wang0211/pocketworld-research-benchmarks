#!/bin/bash
# 诊断:让两个引擎建模同一个总加计延迟再比(旧写法自带约 +5 ms)。新 + 加计 −21 ms ⇔ 旧 + −16;旧 + 加计 −11 ms ⇔ 新 + −16。
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
for d in -4 -3 -5 -2 -6 -1 -7 0 -8; do for sc in 13f5 6d18 7353; do
  n=$( [ $d -lt 0 ] && echo m${d#-} || echo p$d )
  $P/tools/run.sh ${sc}_okvis_as21_sw$n $sc okvis_as_nothr --pace 0 --acc-shift-ms -21 --td-extra-ms $d | head -1
done; done
for d in 0 1 -1 2 -2 3 -3 4 -4; do for sc in 13f5 6d18 7353; do
  n=$( [ $d -lt 0 ] && echo m${d#-} || echo p$d )
  $P/tools/run.sh ${sc}_base_as11_sw$n $sc base_as_nothr --pace 0 --acc-shift-ms -11 --td-extra-ms $d | head -1
done; done
echo BATCH_ACCSH2_DONE
