#!/bin/bash
# evalall.sh <rec_id_prefix e.g. 6e2d> <arkit_ref> <g0> <arms...>   (gap list from $GAPS: "name:g1 ...")
SP=$(dirname "$0"); rec=$1; ref=$2; g0=$3; shift 3
for g in $GAPS; do n=${g%%:*}; g1=${g##*:}
  for arm in "$@"; do f=$SP/out/${arm}_${rec}_$n.tum; [ -f "$f" ] && /usr/bin/python3 $SP/gapeval.py "$f" "$ref" $g0 $g1 "${arm}_$n" | grep -v "^  poses"; done
done
