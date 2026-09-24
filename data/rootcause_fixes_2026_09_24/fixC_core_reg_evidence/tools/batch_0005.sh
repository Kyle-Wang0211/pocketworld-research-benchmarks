#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
C=cap_1789119308200005
tools/run_phone.sh jpeg ph_$C $C j_base_$C 0-6
tools/run_phone.sh jpeg ph_${C}_u06 $C j_u06_$C 0-6
tools/run_phone.sh jpeg ph_${C}_u06 $C j_u06a_$C 0-6 OFFICIAL_AETHER_REG_EVIDENCE=1
tools/run_phone.sh jpeg ph_${C}_u06 $C j_u06b_$C 0-6 OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
tools/run_phone.sh resume - $C r_base_$C -
tools/run_phone.sh resume - $C r_u06_$C 0-6
tools/run_phone.sh jpeg ph_${C}_uB $C j_uB_$C 0-6,22
echo BATCH_0005_DONE
