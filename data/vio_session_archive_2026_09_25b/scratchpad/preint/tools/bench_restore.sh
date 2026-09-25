#!/bin/bash
# bench_restore.sh <backup_dir>:按快照还原台架目录并自证(逐文件 sha256、符号链接逐条、范围内多出的文件删掉)。
set -euo pipefail
B=$HOME/Developer/arloopbench; O="$1"; cd "$B"
# 1) 范围内同步/pod install 新增的文件:不在快照清单里的删掉(只删普通文件,不碰构建缓存)
{ find . -path ./build -prune -o -path ./.dart_tool -prune -o -path ./ios/Pods -prune -o -path ./ios/.symlinks -prune -o -type f -print
  find ./ios/Pods/Pods.xcodeproj "./ios/Pods/Target Support Files" ./ios/Pods/Manifest.lock "./ios/Pods/Local Podspecs" -type f 2>/dev/null
} | sed 's|^\./||' | LC_ALL=C sort > "$O/list_after.txt"
comm -13 "$O/list.txt" "$O/list_after.txt" > "$O/added.txt"
while IFS= read -r f; do [ -n "$f" ] && rm -f -- "$f"; done < "$O/added.txt"
# 2) 文件原样解回
tar -xf "$O/bench_files.tar"
# 3) 符号链接:快照里有的逐条恢复;快照里没有、现在多出来的删掉
while IFS=$'\t' read -r l t; do ln -sfn "$t" "$l"; done < "$O/symlinks.tsv"
find . -path ./build -prune -o -path ./.dart_tool -prune -o -path ./ios/Pods -prune -o -type l -print | sed 's|^\./||' | LC_ALL=C sort | \
  while read -r l; do grep -q "^$(printf '%s' "$l" | sed 's/[][\.*^$]/\\&/g')	" "$O/symlinks.tsv" || { echo "删多出的链接 $l"; rm -f -- "$l"; }; done
# 4) 自证
bad=0
shasum -a 256 -c "$O/files.sha256" > "$O/verify.txt" 2>&1 || bad=1
nf=$(grep -c ': OK$' "$O/verify.txt" || true)
ns=0; while IFS=$'\t' read -r l t; do [ "$(readlink "$l")" = "$t" ] && ns=$((ns+1)) || { echo "链接不符 $l"; bad=1; }; done < "$O/symlinks.tsv"
echo "restore: 删新增文件 $(grep -c . "$O/added.txt" || true) 个;$nf/$(wc -l < "$O/files.sha256") 个文件逐字节一致;$ns/$(wc -l < "$O/symlinks.tsv") 条链接一致;bad=$bad"
