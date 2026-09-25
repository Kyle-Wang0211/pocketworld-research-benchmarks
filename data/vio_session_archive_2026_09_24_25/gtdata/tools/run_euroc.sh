#!/bin/bash
# run_euroc.sh <L=S|M> <slam.yaml> <device.yaml> <euroc_dir> <out.tum>  (file-based reader, under shared lock)
W=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/gtdata
L=$1; shift
$W/tools/locked.sh $W/work/build-$L/pw_euroc_runner "$1" "$2" "euroc://$3" "$4" > "$4.log" 2>&1
echo "rc=$? $(wc -l < $4) poses -> $4"
