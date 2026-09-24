#!/bin/bash
for d in "$@"; do
  n=$(basename $d)
  if [ -f /root/fss_runs/$n/filt/mesh.obj ]; then
    /venv/main/bin/python /root/layer2.py /root/fss_runs/$n/filt/mesh.obj "$n" --objframe
  else
    echo "$n : NO MESH"
  fi
done
