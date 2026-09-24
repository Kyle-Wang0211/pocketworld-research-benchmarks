#!/bin/bash
cd /root/aline_lodbuild
bash srv_build.sh | tail -1
for cfg in "t4_cap1M --threads 4 --ring-mb 64 --backlog-mb 256 --chunk-cap 1000000" "t1_cap1M --threads 1 --ring-mb 64 --backlog-mb 128 --chunk-cap 1000000"; do
  set -- $cfg; TAG=216M_$1; shift
  bash srv_equiv.sh /root/pc_216M.las $TAG /root/aline_lodbuild/nf_216M_run1 "$@"
  rm -rf /root/aline_lodbuild/port_$TAG
done
touch MATRIX216.DONE
