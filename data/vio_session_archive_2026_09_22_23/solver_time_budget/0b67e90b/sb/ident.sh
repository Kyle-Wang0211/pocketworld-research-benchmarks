#!/bin/bash
# OFF 逐位同 —— 用离线档(1.0e6 s / 30 次)⇒ 没有任何墙钟判据,结果与机器负载无关
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sb
cd $S
for sc in V1_01 V1_02 V1_03 6e2d4b99; do
  ./run1.sh base $sc upstream 1 2>&1 | grep -v Segmentation
  ./run1.sh branch $sc upstream 1
done
echo IDENT_DONE
