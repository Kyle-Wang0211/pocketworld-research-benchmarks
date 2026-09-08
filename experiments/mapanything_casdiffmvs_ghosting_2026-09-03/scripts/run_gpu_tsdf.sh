#!/bin/bash
cd /root/regionmerge
for e in casdiff maprime pda; do
  echo "### $e"
  /venv/main/bin/python tsdf_gpu.py /root/regionmerge/gated_$e /root/regionmerge/tsdf ${e}_g3mm
done
echo GPU_TSDF_DONE
