#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
until grep -q BATCH_BIG1_DONE logs/batch_big1.log 2>/dev/null; do sleep 20; done
# Mac recording, product cadence + controls (fast)
for F in S_prod74_Xhost S_prod_A S_prod_Xhost; do
  tools/run_mac.sh $F base_$F; tools/run_mac.sh $F a_$F OFFICIAL_AETHER_REG_EVIDENCE=1; tools/run_mac.sh $F b_$F OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
done
for F in S_prod74_A_shuf S_prod74_Xhost_shuf S_prod_Xdev; do
  tools/run_mac.sh $F base_$F; tools/run_mac.sh $F a_$F OFFICIAL_AETHER_REG_EVIDENCE=1; tools/run_mac.sh $F b_$F OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
done
# other JPEG phone captures
for C in cap_1788795741337526 cap_1787733401226757; do
  tools/run_phone.sh jpeg ph_$C $C j_base_$C -
  tools/run_phone.sh jpeg ph_$C $C j_a_$C - OFFICIAL_AETHER_REG_EVIDENCE=1
  tools/run_phone.sh jpeg ph_$C $C j_b_$C - OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
  tools/run_phone.sh resume - $C r_base_$C -
done
# second big capture (lepton): free the first capture's decoded JPEGs, decode, run
rm -rf lepton/jpg_cap_1786013666212373
C=cap_1786199789306631
/usr/bin/python3 tools/lepton_feed.py $C
tools/run_phone.sh jpeg lp_$C $C j_base_$C -
tools/run_phone.sh jpeg lp_$C $C j_a_$C - OFFICIAL_AETHER_REG_EVIDENCE=1
tools/run_phone.sh jpeg lp_$C $C j_b_$C - OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
tools/run_phone.sh resume - $C r_base_$C -
rm -rf lepton/jpg_$C
# Mac recording, 0.25 s cadence (slow)
for F in S_deb74_A S_deb74_Xhost S_deb_A S_deb_Xhost; do
  tools/run_mac.sh $F base_$F; tools/run_mac.sh $F a_$F OFFICIAL_AETHER_REG_EVIDENCE=1; tools/run_mac.sh $F b_$F OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
done
echo BATCH_REST_DONE
