#!/bin/bash
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libtbb.so.12
export PYTHONPATH=/root/vdbpkg
cd /root/regionmerge
for e in casdiff maprime pda; do
  VOXEL=0.01 STRIDE=2 MIN_WEIGHT=3.0 /venv/main/bin/python tsdf_vdb.py /root/regionmerge/gated_$e /root/regionmerge/tsdf $e
  /venv/main/bin/python carve_filter.py /root/regionmerge/tsdf/${e}_raw.ply \
      /root/regionmerge/tsdf/${e}_vdb_carve1_verts.npy /root/regionmerge/tsdf/${e}_carved_points.ply 0.015
done
echo VDB_ALL_DONE
