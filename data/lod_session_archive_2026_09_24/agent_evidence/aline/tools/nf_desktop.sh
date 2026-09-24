#!/bin/bash
# A-line noise floor: run the desktop PotreeConverter (8bfad98, compile-only patch)
# twice on the same LAS and compare the two trees node-by-node.
# Writes only under /root/aline_lodbuild.
set -u
W=/root/aline_lodbuild
PC=/root/pc2/build/PotreeConverter
IN=${1:-/root/pc_t3_36M.las}
TAG=${2:-36M}
cd $W
for r in 1 2; do
  rm -rf $W/nf_${TAG}_run$r
  /usr/bin/time -v $PC $IN -o $W/nf_${TAG}_run$r --attributes rgb > $W/nf_${TAG}_run$r.log 2> $W/nf_${TAG}_run$r.time
  echo "run$r rc=$? $(grep -e 'Elapsed' -e 'Maximum resident' $W/nf_${TAG}_run$r.time | tr '\n' ' ')"
done
python3 $W/compare_octrees.py --selftest $W/nf_${TAG}_run1
python3 $W/compare_octrees.py $W/nf_${TAG}_run1 $W/nf_${TAG}_run2 --json $W/nf_${TAG}.json > /dev/null
cat $W/nf_${TAG}.json
touch $W/NF_${TAG}.DONE
