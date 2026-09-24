#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
R=tools/run_phone2.sh
C=cap_1787733401226757
$R pdb pdb_$C $C p_base_$C 0-3
$R pdb pdb_${C}_u03 $C p_u03_$C 0-3
$R pdb pdb_${C}_u03 $C p_u03a_$C 0-3 OFFICIAL_AETHER_REG_EVIDENCE=1
$R pdb pdb_${C}_u03 $C p_u03b_$C 0-3 OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
$R resume - $C r_u03_$C 0-3
$R jpeg ph_${C}_u03 $C j_u03_$C 0-3
C=cap_1789119308200005
$R pdb pdb_$C $C p_base_$C 0-8
$R pdb pdb_${C}_uB2 $C p_uB2_$C 0-8
$R pdb pdb_${C}_uB2 $C p_uB2a_$C 0-8 OFFICIAL_AETHER_REG_EVIDENCE=1
$R pdb pdb_${C}_uB2 $C p_uB2b_$C 0-8 OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
echo BATCH_U03_DONE
