#!/bin/bash
# 混合臂(诊断):PW_MIX_NEW 选哪些调用点用新积分器;PW_DIAG_LOG 逐帧日志。单线程,--pace 0。
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
one() { # <arm> <delta> <scene>
  local arm=$1 d=$2 sc=$3 n; n=$( [ $d -lt 0 ] && echo m${d#-} || echo p$d )
  local tag=${sc}_mix${arm}_sw$n
  PW_MIX_NEW=$arm PW_DIAG_LOG=$P/runs/diaglog/$tag.log $P/tools/run.sh $tag $sc mix_nothr --td-extra-ms $d --pace 0 | head -1
}
# 1) 自证:全旧 = 8ebac9a、全新 = 4e8dda2(Δ = 0 / −5)
for d in 0 -5; do for sc in 13f5 6d18 7353; do one none $d $sc; one all $d $sc; done; done
echo BATCH_MIX_VALID_DONE
# 2) 只换一处:backend / front / init 扫 Δ = −8…+2;prop 只跑 0 / −5
for d in 0 -5 -3 -6 -1 1 -4 -2 -7 2 -8; do for sc in 13f5 6d18 7353; do
  for arm in backend front init; do one $arm $d $sc; done
done; done
for d in 0 -5; do for sc in 13f5 6d18 7353; do one prop $d $sc; done; done
echo BATCH_MIX_DONE
