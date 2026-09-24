#!/bin/bash
# remaining 0.25 s arms (resumed session); waits for the orphaned runs to finish first
cd /private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
until [ -f runs/base_S_deb_A/metrics.json ] && ! pgrep -f "b_S_deb74_Xhost" >/dev/null; do sleep 15; done
[ -f runs/b_S_deb74_Xhost/metrics.json ] || { /usr/bin/python3 tools/fixc_metrics.py runs/b_S_deb74_Xhost mac base_sfmB/inputs/feed_S_deb74_Xhost.jsonl | tail -1; tools/clean_big.sh runs/b_S_deb74_Xhost; }
tools/run_mac.sh S_deb_A a_S_deb_A OFFICIAL_AETHER_REG_EVIDENCE=1
tools/run_mac.sh S_deb_A b_S_deb_A OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
for F in S_deb_Xhost; do
  tools/run_mac.sh $F base_$F; tools/run_mac.sh $F a_$F OFFICIAL_AETHER_REG_EVIDENCE=1; tools/run_mac.sh $F b_$F OFFICIAL_AETHER_FINALIZE_VIA_RESUME=1
done
echo BATCH_DEB_DONE
