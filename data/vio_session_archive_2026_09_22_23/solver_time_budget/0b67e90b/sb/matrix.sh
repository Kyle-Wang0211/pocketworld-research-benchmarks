#!/bin/bash
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sb
cd $S
ARMS="prod prod_b0.035 prod_b0.0233 prod_b0.010 prod_b0.005 prod_b0"
for rep in 1 2 3; do
  for sc in 6e2d4b99 V1_01 V1_02 V1_03; do
    ./run1.sh basenr $sc prod $rep
    for a in $ARMS; do ./run1.sh branch $sc $a $rep; done
  done
  echo "rep $rep done $(date) df=$(df -h ~ | tail -1 | awk '{print $4}')"
done
echo MATRIX_DONE
