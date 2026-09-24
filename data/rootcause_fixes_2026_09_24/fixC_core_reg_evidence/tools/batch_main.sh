#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
R=tools/run_phone2.sh
# 1-2. big captures, live route replayed with the capture's own (phone) features
for C in cap_1786013666212373 cap_1786199789306631; do
  $R pdb pdb_$C $C p_base_$C -
  $R pdb pdb_$C $C p_a_$C - OFFICIAL_AETHER_REG_EVIDENCE=1
  $R pdb pdb_$C $C p_b_$C - OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
  $R resume - $C r_base_$C -
done
# 3. Mac recording, product cadence + controls
for F in S_prod74_Xhost S_prod_A S_prod_Xhost S_prod74_A_shuf S_prod74_Xhost_shuf S_prod_Xdev; do
  tools/run_mac.sh $F base_$F; tools/run_mac.sh $F a_$F OFFICIAL_AETHER_REG_EVIDENCE=1; tools/run_mac.sh $F b_$F OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
done
# 4. small captures, phone features
for C in cap_1788795741337526 cap_1787733401226757; do
  $R pdb pdb_$C $C p_base_$C -
  $R pdb pdb_$C $C p_a_$C - OFFICIAL_AETHER_REG_EVIDENCE=1
  $R pdb pdb_$C $C p_b_$C - OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
done
echo MAIN_PART1_DONE
# 5. Mac recording, 0.25 s cadence (slow)
for F in S_deb74_A S_deb74_Xhost S_deb_A S_deb_Xhost; do
  tools/run_mac.sh $F base_$F; tools/run_mac.sh $F a_$F OFFICIAL_AETHER_REG_EVIDENCE=1; tools/run_mac.sh $F b_$F OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
done
# 6. small captures, JPEG (Mac features)
for C in cap_1788795741337526 cap_1787733401226757; do
  $R jpeg ph_$C $C j_base_$C -
  $R jpeg ph_$C $C j_a_$C - OFFICIAL_AETHER_REG_EVIDENCE=1
  $R jpeg ph_$C $C j_b_$C - OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
done
echo BATCH_MAIN_DONE
