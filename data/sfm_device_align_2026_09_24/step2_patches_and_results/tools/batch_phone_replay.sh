#!/bin/bash
# Task B: replay tripped phone captures (JPEG mode) through the patched core (σ via covariance path), sequentially.
cd "$(dirname "$0")/.."
clean() { find runs/$1 -type f -size +5M -print0 | while IFS= read -r -d '' f; do
  echo "  rm >5MB $(stat -f %z "$f") $(shasum -a 256 "$f" | cut -c1-16) $f"; rm -f "$f"; done; }
for c in "$@"; do
  ./tools/run_arm_jpeg.sh ph_$c phr_$c; clean phr_$c; df -h ~ | tail -1 | awk '{print "  df avail " $4}'
done
echo PHONE_REPLAY_DONE
