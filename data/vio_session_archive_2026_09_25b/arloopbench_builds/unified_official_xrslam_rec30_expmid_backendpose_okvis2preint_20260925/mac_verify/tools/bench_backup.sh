#!/bin/bash
# bench_backup.sh <backup_dir>:台架目录同步前快照(照集成 agent 的做法:文件清单 + tar + 逐文件 sha256 + 符号链接表)。
# 范围:除 build/、.dart_tool/、ios/.symlinks/、ios/Pods/<第三方源码> 外的全部普通文件,再加 Pods 的
# 工程/配置文件(pod install 会改的那几处)。构建缓存不在还原范围。
set -euo pipefail
B=$HOME/Developer/arloopbench; O="$1"; mkdir -p "$O"; cd "$B"
{ find . -path ./build -prune -o -path ./.dart_tool -prune -o -path ./ios/Pods -prune -o -path ./ios/.symlinks -prune -o -type f -print
  find ./ios/Pods/Pods.xcodeproj "./ios/Pods/Target Support Files" ./ios/Pods/Manifest.lock "./ios/Pods/Local Podspecs" -type f 2>/dev/null
} | sed 's|^\./||' | LC_ALL=C sort > "$O/list.txt"
tr '\n' '\0' < "$O/list.txt" | xargs -0 shasum -a 256 > "$O/files.sha256"
tar -cf "$O/bench_files.tar" -T "$O/list.txt" 2> "$O/tar.err"
find . -path ./build -prune -o -path ./.dart_tool -prune -o -path ./ios/Pods -prune -o -type l -print | sed 's|^\./||' | LC_ALL=C sort | \
  while read -r l; do printf '%s\t%s\n' "$l" "$(readlink "$l")"; done > "$O/symlinks.tsv"
shasum -a 256 "$O/bench_files.tar" > "$O/SHA256.txt"
echo "backup: $(wc -l < "$O/list.txt") files, $(wc -l < "$O/symlinks.tsv") symlinks -> $O"
