#!/bin/bash
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/scaleS2
B=$S/tools/build_variant.sh
$B ios OFF 1 0 2>&1 | tail -4
$B ios_thr ON 1 0 2>&1 | tail -4
$B off_thr ON 0 0 2>&1 | tail -4
$B official ON 1 1 2>&1 | tail -4
$B gen_fm OFF 0 1 2>&1 | tail -4
$B ios_fm OFF 1 1 2>&1 | tail -4
echo ALL_DONE
