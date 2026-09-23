#!/bin/bash
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/373814b7-9e8a-4c30-8bed-61f68566515c/scratchpad/sb2
cd $SP
chk() { local a; a=$(df -k ~ | tail -1 | awk '{print $4}'); if [ "$a" -lt 1572864 ]; then echo "DISK_LOW $(df -h ~ | tail -1)"; exit 3; fi; }
ARMS_1="basenr:prod branch:prod branch:prod_b0.035 branch:prod_b0.0233 branch:prod_b0.0117"
ARMS_2="branch:prod_b0.0117 branch:prod_b0.0233 branch:prod_b0.035 branch:prod basenr:prod"
ARMS_3="branch:prod_b0.035 basenr:prod branch:prod_b0.0117 branch:prod branch:prod_b0.0233"
for rep in 1 2 3; do
  eval ARMS=\$ARMS_$rep
  for sc in V1_01 V1_02 V1_03 6e2d4b99; do
    for ba in $ARMS; do chk; ./run1.sh ${ba%%:*} $sc ${ba##*:} $rep; done
  done
  echo "rep $rep done $(date) df=$(df -h ~ | tail -1 | awk '{print $4}')"
done
echo "== offline identity (1.0e6 s / 30 it: no wall-clock criterion anywhere)"
for sc in V1_01 V1_02 V1_03 6e2d4b99; do chk; ./run1.sh basenr $sc upstream 1; ./run1.sh branch $sc upstream 1; done
echo MATRIX_DONE
