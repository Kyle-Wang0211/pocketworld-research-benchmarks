#!/bin/bash
# run1.sh <runner> <slam.yaml> <dev.yaml> <euroc_dir> <out_prefix>
"$1" "$2" "$3" "euroc://$4" "$5.tum" > "$5.log" 2>&1
echo "rc=$? $(wc -l < "$5.tum") poses  $(shasum -a 256 "$5.tum" | cut -c1-16)  $5"
