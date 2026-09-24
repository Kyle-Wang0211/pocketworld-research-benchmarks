#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
until grep -q BATCH_0005_DONE logs/batch_0005.log 2>/dev/null; do sleep 20; done
C=cap_1789119308200005
tools/run_phone.sh jpeg ph_${C}_uB2 $C j_uB2_$C 0-8
tools/run_phone.sh jpeg ph_${C}_uB2 $C j_uB2a_$C 0-8 OFFICIAL_AETHER_REG_EVIDENCE=1
tools/run_phone.sh jpeg ph_${C}_uB2 $C j_uB2b_$C 0-8 OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
tools/run_phone.sh resume - $C r_uB2_$C 0-8
C=cap_1787733401226757
tools/run_phone.sh jpeg ph_${C}_u0 $C j_u0_$C 0
tools/run_phone.sh jpeg ph_${C}_u0 $C j_u0a_$C 0 OFFICIAL_AETHER_REG_EVIDENCE=1
tools/run_phone.sh jpeg ph_${C}_u0 $C j_u0b_$C 0 OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
tools/run_phone.sh resume - $C r_u0_$C 0
echo BATCH_EXTRA_DONE
