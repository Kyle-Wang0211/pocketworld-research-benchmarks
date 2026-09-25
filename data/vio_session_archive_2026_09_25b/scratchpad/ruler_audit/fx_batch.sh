#!/bin/bash
RA=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/ruler_audit
for sa in "13f5 1.0133 1.0270" "6d18 1.0064 1.0154" "7353 1.0169 1.0247"; do
  set -- $sa; sc=$1; ag=$2; aa=$3
  for cfg in "scall_am16_swm4 all -16 -4" "scall_ap0_swm4 all 0 -4" "scnone_ap0_swp0 none 0 0"; do
    set -- $cfg; name=$1; mix=$2; a=$3; d=$4
    for al in 1 $ag $aa; do
      tag=${sc}_${name}_a${al}
      [ -s $RA/fx_runs/$tag.backend.csv ] && continue
      if [ $al = 1 ]; then nice -n 5 $RA/ra_run.sh $tag $sc $mix $a $d; else nice -n 5 $RA/ra_run.sh $tag $sc $mix $a $d --k-scale 0 1e9 $al; fi
    done
  done
  for al in 0.98 0.99 1.01 1.02 1.03 1.04; do nice -n 5 $RA/ra_run.sh ${sc}_scall_am16_swm4_s${al} $sc all -16 -4 --k-scale 0 1e9 $al; done
done
echo FX_BATCH_DONE
