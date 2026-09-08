#!/bin/bash
cd /root/regionmerge
for e in casdiff maprime pda; do
  /venv/main/bin/python points_from_gated.py /root/regionmerge/gated_$e /root/regionmerge/tsdf/${e}_raw.ply
done
echo RAW_CLOUDS_DONE
for e in casdiff maprime pda; do
  VOXEL=0.003 TRUNC=0.04 /venv/main/bin/python tsdf_o3d.py /root/regionmerge/gated_$e /root/regionmerge/tsdf ${e}3mm
done
echo TSDF3MM_ALL_DONE
