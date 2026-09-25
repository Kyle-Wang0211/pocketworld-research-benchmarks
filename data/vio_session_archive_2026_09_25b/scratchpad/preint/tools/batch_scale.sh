#!/bin/bash
# 尺度缩小的诊断回放:诊断引擎(混合臂构建,开关不设 = 4e8dda2 逐位)+ 加计平移 + 逐帧日志(初始化尺度 / 重力 / 零偏)
P=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/preint
one() { # <mix> <accshift> <delta> <scene>
  local mix=$1 a=$2 d=$3 sc=$4 n an; n=$( [ $d -lt 0 ] && echo m${d#-} || echo p$d ); an=$( [ $a -lt 0 ] && echo m${a#-} || echo p$a )
  local tag=${sc}_sc${mix}_a${an}_sw$n
  if [ $mix = all ]; then
    env -u PW_MIX_NEW PW_DIAG_LOG=$P/runs/diaglog/$tag.log $P/tools/run.sh $tag $sc mixas_nothr --pace 0 --acc-shift-ms $a --td-extra-ms $d | head -1
  else
    PW_MIX_NEW=none PW_DIAG_LOG=$P/runs/diaglog/$tag.log $P/tools/run.sh $tag $sc mixas_nothr --pace 0 --acc-shift-ms $a --td-extra-ms $d | head -1
  fi
}
# 自证:平移 0、全新、Δ=−5 应与 4e8dda2 同 Δ 逐位相同
one all 0 -5 13f5
# 新引擎 Δ = −4:加计平移量扫描(0…−24 ms)
for a in -16 0 -8 -24 -4 -12 -20; do for sc in 13f5 6d18 7353; do one all $a -4 $sc; done; done
# 旧引擎 Δ = 0:加计 −16 与 0(带日志)
for a in -16 0; do for sc in 13f5 6d18 7353; do one none $a 0 $sc; done; done
echo BATCH_SCALE_DONE
