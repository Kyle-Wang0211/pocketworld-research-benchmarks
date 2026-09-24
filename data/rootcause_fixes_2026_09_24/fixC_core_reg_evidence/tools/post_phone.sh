#!/bin/bash
# post_phone.sh — recon-only pairwise check for every phone run (+ cross-session pairs for the mixed capture).
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixC
cd $W/runs
for d in [jrp]_*_cap_*; do
  cap=cap_${d##*_cap_}; mode=${d%%_*}; arm=${d#*_}; arm=${arm%%_cap_*}
  case $mode in j) f=$(ls $W/inputs/feed_ph_${cap}.jsonl $W/inputs/feed_lp_${cap}.jsonl 2>/dev/null | head -1);; r) f=$W/inputs/feed_rs_${cap}.jsonl;; p) f=$W/inputs/feed_pdb_${cap}.jsonl;; esac
  ut=""
  case "$cap:$arm" in
    cap_1789119308200005:uB2*) ut="--untrusted=0-8";;
    cap_1789119308200005:*) ut="--untrusted=0-6";;
    cap_1787733401226757:u03*|cap_1787733401226757:base) ut="--untrusted=0-3";;
    cap_1787733401226757:u0*) ut="--untrusted=0";;
  esac
  /usr/bin/python3 $W/tools/relpose_recon_only.py $W/runs/$d $f $cap $ut 2>&1 | cut -c1-300
  if [ "$cap" = cap_1789119308200005 ]; then
    sp=0-6; case $arm in uB2*) sp=0-8;; esac
    /usr/bin/python3 $W/tools/cross_pairs.py $W/runs/$d $f $cap $sp 2>&1 | cut -c1-200
  fi
done
