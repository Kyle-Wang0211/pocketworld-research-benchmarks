#!/bin/bash
# Task A, 0.25 s S_deb* arms at σ=0.040 (covariance path). Sequential; >5 MB files removed after each arm.
cd "$(dirname "$0")/.."
R=./tools/run_arm.sh
clean() { find runs/$1 -type f -size +5M -print0 | while IFS= read -r -d '' f; do
  echo "  rm >5MB $(stat -f %z "$f") $(shasum -a 256 "$f" | cut -c1-16) $f"; rm -f "$f"; done; }
arm() { $R "$@"; clean $2; df -h ~ | tail -1 | awk '{print "  df avail " $4}'; }
arm S_deb74_A cov_S_deb74_A
arm S_deb74_Xhost cov_S_deb74_Xhost
arm S_deb_A cov_S_deb_A
arm S_deb_Xhost cov_S_deb_Xhost
arm S_deb74_A_x110 cov_S_deb74_A_x110
echo DEB_DONE
