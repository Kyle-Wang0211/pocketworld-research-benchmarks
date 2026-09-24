#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
R=tools/run_phone2.sh
C=cap_1784820775062947
$R pdb pdb_$C $C p_base_$C -
$R pdb pdb_$C $C p_a_$C - OFFICIAL_AETHER_REG_EVIDENCE=1
$R pdb pdb_$C $C p_b_$C - OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
echo BATCH_4820_DONE
