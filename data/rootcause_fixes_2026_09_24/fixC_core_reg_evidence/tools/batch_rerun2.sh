#!/bin/bash
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
until grep -q BATCH_0005_DONE logs/batch_0005.log 2>/dev/null; do sleep 20; done
C=cap_1789119308200005
tools/run_phone2.sh jpeg ph_${C}_u06 $C j_u06bv2_$C 0-6 OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
tools/run_phone2.sh resume - $C r_u06v2_$C 0-6
echo BATCH_RERUN2_DONE
