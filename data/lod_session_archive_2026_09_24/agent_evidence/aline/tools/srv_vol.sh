#!/bin/bash
# D11 stress: volumetric cloud where one node accepts > 1,000,000 points.
set -u
W=/root/aline_lodbuild; N=${1:-16000000}; cd $W
[ -f vol.ply ] || python3 vol_gen.py vol.ply $N
[ -f vol.las ] || python3 ply2las_repo.py vol.ply vol.las
rm -rf port_vol_ply port_vol_ply_chunks
/usr/bin/time -v bin/pwlod_build_cli vol.ply port_vol_ply --chunkdir port_vol_ply_chunks --threads 32 > port_vol_ply.log 2> port_vol_ply.time
echo "port(PLY) rc=$? $(cat port_vol_ply.log) $(grep -e Elapsed -e 'Maximum resident' port_vol_ply.time | tr '\n' ' ')"
python3 max_node.py port_vol_ply
python3 verify_lossless_repo.py port_vol_ply vol.ply | tail -12
python3 verify_colour_repo.py port_vol_ply vol.ply | tail -6
touch VOL.DONE
# desktop PotreeConverter on the same cloud via LAS (upstream has the unbounded dbgAccepted write)
rm -rf desk_vol port_vol_las port_vol_las_chunks
/usr/bin/time -v /root/pc2/build/PotreeConverter vol.las -o desk_vol --attributes rgb > desk_vol.log 2> desk_vol.time
echo "desktop rc=$? $(grep -e Elapsed -e 'Maximum resident' -e 'Exit status' desk_vol.time | tr '\n' ' ')"
tail -3 desk_vol.log
/usr/bin/time -v bin/pwlod_build_cli vol.las port_vol_las --chunkdir port_vol_las_chunks --threads 32 > port_vol_las.log 2> port_vol_las.time
echo "port(LAS) rc=$? $(cat port_vol_las.log)"
[ -f desk_vol/metadata.json ] && python3 compare_octrees.py desk_vol port_vol_las --json equiv_vol.json > /dev/null && python3 -c "import json; r=json.load(open('equiv_vol.json')); print({k:r[k] for k in ['nodes_A','nodes_B','nodes_only_A','nodes_only_B','count_diff_nodes','full_multiset_diff_nodes','full_multiset_diff_points','pos_multiset_diff_points','global_multiset_diff_points','octree_bin_A','octree_bin_B']}); print('worst', r['worst_nodes'][:5])"
[ -f desk_vol/metadata.json ] && python3 max_node.py desk_vol
touch VOL2.DONE
