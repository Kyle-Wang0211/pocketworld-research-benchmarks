#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
C=cap_1786013666212373
tools/run_phone.sh jpeg lp_$C $C j_base_$C -
tools/run_phone.sh jpeg lp_$C $C j_a_$C - OFFICIAL_AETHER_REG_EVIDENCE=1
tools/run_phone.sh jpeg lp_$C $C j_b_$C - OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
tools/run_phone.sh resume - $C r_base_$C -
echo BATCH_BIG1_DONE
