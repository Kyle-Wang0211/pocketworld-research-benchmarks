#!/bin/bash
cd /root/regionmerge
# control: filter by the NON-carved surface too, so carving's own effect is isolated
for e in casdiff maprime pda; do
  echo "### $e carve0 control"
  /venv/main/bin/python carve_filter.py /root/regionmerge/tsdf/${e}_raw.ply \
      /root/regionmerge/tsdf/${e}_vdb_carve0_verts.npy /root/regionmerge/tsdf/${e}_nocarve_points.ply 0.015
done
echo CARVE0_CONTROL_DONE
# 3 mm TSDF, strictly one at a time (the cgroup cap is 64.5 GB and two at once OOMs)
for e in casdiff pda; do
  echo "### $e 3mm"
  VOXEL=0.003 TRUNC=0.04 /venv/main/bin/python tsdf_o3d.py /root/regionmerge/gated_$e /root/regionmerge/tsdf ${e}3mm
done
echo FINISH_ALL_DONE
