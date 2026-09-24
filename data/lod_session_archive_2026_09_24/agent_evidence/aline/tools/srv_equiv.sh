#!/bin/bash
# port vs desktop on the same LAS: srv_equiv.sh <las> <tag> <desktop_ref_dir> [cli options...]
set -u
W=/root/aline_lodbuild; IN=$1; TAG=$2; REF=$3; shift 3
rm -rf $W/port_$TAG $W/port_${TAG}_chunks
/usr/bin/time -v $W/bin/pwlod_build_cli $IN $W/port_$TAG --chunkdir $W/port_${TAG}_chunks "$@" > $W/port_$TAG.log 2> $W/port_$TAG.time
echo "rc=$? $(cat $W/port_$TAG.log) $(grep -e 'Elapsed' -e 'Maximum resident' $W/port_$TAG.time | tr '\n' ' ')"
python3 $W/compare_octrees.py $REF $W/port_$TAG --json $W/equiv_$TAG.json > /dev/null
python3 - $W/equiv_$TAG.json <<'PY'
import json,sys; r=json.load(open(sys.argv[1]))
keys=['nodes_A','nodes_B','nodes_only_A','nodes_only_B','count_diff_nodes','full_multiset_diff_nodes','full_multiset_diff_points','pos_multiset_diff_nodes','pos_multiset_diff_points','bytesize_vs_numPoints_mismatch','octree_bin_A','octree_bin_B','global_multiset_diff_points','scale_equal','offset_equal']
print({k:r[k] for k in keys}); print('worst', r['worst_nodes'][:5]); print('onlyA', r['nodes_only_A_list'][:8]); print('onlyB', r['nodes_only_B_list'][:8])
PY
diff <(grep -v '"name"' $REF/metadata.json) <(grep -v '"name"' $W/port_$TAG/metadata.json) > $W/equiv_$TAG.metadiff && echo "METADATA identical except name" || { echo "METADATA DIFF:"; head -20 $W/equiv_$TAG.metadiff; }
