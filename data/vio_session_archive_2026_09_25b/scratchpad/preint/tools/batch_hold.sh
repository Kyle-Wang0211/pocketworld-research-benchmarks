#!/bin/bash
# 诊断:后端残差 = OKVIS2 结构 + 段内右端样本保持(PW_DIAG_HOLD);前端 / 初始化 / 外推保持旧写法(PW_MIX_NEW=backend)
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
until grep -q BATCH_MIX_DONE $P/runs/batch_mix.out 2>/dev/null; do sleep 5; done
# 自证:不设 PW_DIAG_HOLD、PW_MIX_NEW 不设(全新)⇒ 应与 4e8dda2 逐位相同
env -u PW_DIAG_HOLD -u PW_MIX_NEW $P/tools/run.sh 13f5_mixhold_selfcheck 13f5 mixhold_nothr --pace 0 | head -1
one() { # <hold> <delta> <scene>
  local h=$1 d=$2 sc=$3 n; n=$( [ $d -lt 0 ] && echo m${d#-} || echo p$d )
  local tag=${sc}_hold${h}_sw$n
  PW_MIX_NEW=backend PW_DIAG_HOLD=$h PW_DIAG_LOG=$P/runs/diaglog/$tag.log $P/tools/run.sh $tag $sc mixhold_nothr --td-extra-ms $d --pace 0 | head -1
}
for d in -10 -9 -11 -8 -12 -7 -13 -6 -5; do for sc in 13f5 6d18 7353; do one both $d $sc; done; done
echo BATCH_HOLD_BOTH_DONE
for d in -8 -7 -9 -6 -10 -5 -4 -11 -3; do for sc in 13f5 6d18 7353; do one gyro $d $sc; one acc $d $sc; done; done
echo BATCH_HOLD_DONE
