#!/bin/bash
SP=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/cb65ad40-6d75-486f-b32e-36830fe130aa/scratchpad/aline
for t in 1 2 4; do for cap in 250000 1000000; do
  TAG=g_t${t}_c${cap}
  $SP/tools/mrun.sh $TAG --threads $t --ring-mb 64 --backlog-mb 128 --chunk-cap $cap | tail -1
  /tmp/pf_venv/bin/python $SP/tools/compare_octrees.py $SP/run/m36_t12 $SP/run/$TAG | /tmp/pf_venv/bin/python -c "import json,sys; r=json.load(sys.stdin); print('   vs t12 default:', {k:r[k] for k in ['nodes_only_A','nodes_only_B','count_diff_nodes','full_multiset_diff_points','global_multiset_diff_points']})"
  diff -q $SP/run/m36_t12/metadata.json $SP/run/$TAG/metadata.json > /dev/null && echo "   metadata identical" || echo "   METADATA DIFFERS"
  rm -rf $SP/run/$TAG
done; done
echo GRID_DONE
