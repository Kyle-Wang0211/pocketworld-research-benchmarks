#!/usr/bin/env bash
# Waits for the aria2 queue to drain, verifies every archive byte-for-byte against the GitHub API sizes,
# merges the split zips, extracts to /data/BlendedMVG, deletes each combined zip after a clean unzip,
# then builds + fully health-checks the train/val lists (make_blendmvg_list.py = the pack's own tool).
set -uo pipefail
Z=/data/blendedmvg_zips; OUT=/data/BlendedMVG; PY=/venv/main/bin/python
echo "[$(date)] waiting for aria2c"
while pgrep -x aria2c > /dev/null; do sleep 60; done
echo "[$(date)] aria2c exited; verifying sizes"
$PY - "$Z" <<'PYV'
import os, sys
Z=sys.argv[1]; bad=[]; n=0
for t in ["v1.0.0","v1.0.1","v1.0.2"]:
    for line in open(f"{Z}/.assets_{t}.txt"):
        name,size,url=line.split(); n+=1; p=f"{Z}/{name}"
        if not (os.path.exists(p) and os.path.getsize(p)==int(size)) or os.path.exists(p+".aria2"): bad.append(name)
print(f"verified {n-len(bad)}/{n}; bad: {bad[:10]}")
sys.exit(1 if bad else 0)
PYV
[ $? -eq 0 ] || { echo "ARCHIVES_INCOMPLETE"; exit 1; }
mkdir -p "$OUT"; cd "$Z"
for pair in "BlendedMVS.zip combined_mvs.zip" "BlendedMVS1.zip combined_p1.zip" "BlendedMVS2.zip combined_p2.zip"; do
  set -- $pair
  echo "[$(date)] merging $1"; zip -q -s 0 "$1" --out "$2" || { echo "MERGE_FAILED $1"; exit 1; }
  echo "[$(date)] unzipping $2"; unzip -q -o "$2" -d "$OUT" || { echo "UNZIP_FAILED $2"; exit 1; }
  rm -f "$2"; echo "[$(date)] done $1; scenes now: $(ls "$OUT" | wc -l); free: $(df -h /data | tail -1 | awk '{print $4}')"
done
echo "[$(date)] building lists"
$PY /data/finetune_pack/vendored/make_blendmvg_list.py "$OUT" /data/lists 2>&1 | tail -20
$PY -c 'from PIL import Image; import glob,sys; p=sorted(glob.glob(sys.argv[1]+"/*/blended_images/00000000.jpg"))[0]; print("sample image size", p, Image.open(p).size)' "$OUT"
echo "[$(date)] POST_DONE"
