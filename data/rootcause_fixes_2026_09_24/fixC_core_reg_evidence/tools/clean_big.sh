#!/bin/bash
# clean_big.sh <run_dir> — delete every file >5 MB (after metrics were extracted), log what went.
find "$1" -type f -size +5M -print0 | while IFS= read -r -d '' f; do
  echo "  rm >5MB $(stat -f %z "$f") $(shasum -a 256 "$f" | cut -c1-16) ${f#$1/}"; rm -f "$f"; done
