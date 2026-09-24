#!/bin/bash
# σ = 0.040 m through the upstream per-prior covariance path (exe/sfm.cc:508-515 form,
# device_pose_alignment_v1.h [C2]; user decision 2026-09-24 "用官方参数填 VIO 精度").
# Sequential: timing-dependent budgets in the core => never run arms concurrently.
# After each arm: files > 5 MB are deleted (disk critically low); sizes+sha256 logged first.
cd "$(dirname "$0")/.."
R=./tools/run_arm.sh
clean() { find runs/$1 -type f -size +5M -print0 | while IFS= read -r -d '' f; do
  echo "  rm >5MB $(stat -f %z "$f") $(shasum -a 256 "$f" | cut -c1-16) $f"; rm -f "$f"; done; }
arm() { $R "$@"; clean $2; df -h ~ | tail -1 | awk '{print "  df avail " $4}'; }
arm S_prod74_A cov_S_prod74_A
arm S_prod74_Xhost cov_S_prod74_Xhost
arm S_prod_A cov_S_prod_A
arm S_prod_Xhost cov_S_prod_Xhost
arm S_prod_Xdev cov_S_prod_Xdev
arm S_prod74_A_shuf cov_S_prod74_A_shuf
arm S_prod74_Xhost_shuf cov_S_prod74_Xhost_shuf
arm S_prod74_A_x110 cov_S_prod74_A_x110
arm S_prod74_Xhost_x110 cov_S_prod74_Xhost_x110
arm S_prod74_A cov_S_prod74_A_r2
echo PROD_DONE
if [ "${1:-}" = deb ]; then
  arm S_deb74_A cov_S_deb74_A
  arm S_deb74_Xhost cov_S_deb74_Xhost
  arm S_deb_A cov_S_deb_A
  arm S_deb_Xhost cov_S_deb_Xhost
  arm S_deb74_A_x110 cov_S_deb74_A_x110
fi
echo BATCH_COV040_DONE
