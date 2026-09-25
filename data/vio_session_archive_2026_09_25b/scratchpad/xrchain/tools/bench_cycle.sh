#!/bin/bash
# bench_cycle.sh —— [xrchain] 备份台架 → 四段真源临时指向本 worktree 同步 → 换台架自有文件(本分支快照里改过的 5 份)
#   → PW_XRSLAM_ARM=xrchain pod install → flutter build ios --profile --no-pub → 核验 → 复制到构建目录 → 按备份还原并逐项核对。
#   照抄 any43/tools/bench_cycle_default.sh 的备份 / 还原做法(任一步失败即停,还原由 trap 保证)。🔴 不装机。
set -uo pipefail
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/xrchain
W=/Users/kaidongwang/.config/superpowers/worktrees/pocketworld/bench-xr-recon-chain-20260925
B=/Users/kaidongwang/Developer/arloopbench
OUT=/Users/kaidongwang/Developer/arloopbench_builds/xr_recon_chain_20260925
BASE=/Users/kaidongwang/Developer/arloopbench_builds/unified_official_xrslam_rec30_expmid_any43default_20260925/Runner.app
need() { a=$(df -k ~ | tail -1 | awk '{print $4}'); [ "$a" -ge $((3*1024*1024)) ] || { echo "盘只剩 $((a/1024)) MiB,停"; exit 3; }; }
need
[ -z "$(git -C $W status --porcelain)" ] || { echo "worktree 有未提交改动,停"; exit 4; }
TS=$(date +%Y%m%d_%H%M%S); BK=/Users/kaidongwang/Developer/arloopbench_backups/xrchain_$TS; mkdir -p $BK; echo $BK > $S/BACKUP_DIR.txt
cd $B
find . \( -path ./build -o -path ./.dart_tool \) -prune -o -type f -print | sed 's#^\./##' | LC_ALL=C sort > $BK/list.txt
find . \( -path ./build -o -path ./.dart_tool \) -prune -o -type l -print | sed 's#^\./##' | LC_ALL=C sort | while read l; do printf '%s\t%s\n' "$l" "$(readlink "$l")"; done > $BK/symlinks.tsv
tar -cf $BK/bench_files.tar -T $BK/list.txt 2> $BK/tar.err || { echo "备份 tar 失败"; exit 5; }
( while IFS= read -r f; do shasum -a 256 "$f"; done < $BK/list.txt ) > $BK/files.sha256
shasum -a 256 $BK/bench_files.tar > $BK/SHA256.txt
echo "备份: $BK ($(wc -l < $BK/list.txt) 文件, $(wc -l < $BK/symlinks.tsv) 链接)"
restore() {
  cd $B
  find . \( -path ./build -o -path ./.dart_tool \) -prune -o -type f -print | sed 's#^\./##' | LC_ALL=C sort > $BK/list_before_restore.txt
  comm -13 $BK/list.txt $BK/list_before_restore.txt > $BK/added.txt
  tar -xpf $BK/bench_files.tar
  while IFS=$'\t' read -r l t; do ln -sfn "$t" "$l"; done < $BK/symlinks.tsv
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    if find $B -maxdepth 5 -type l -print0 | xargs -0 readlink | grep -Fq "$f"; then echo "  跳过(有链接指向): $f"; else rm -f "$B/$f" && echo "  删除同步带入: $f"; fi
  done < $BK/added.txt
  # 同步带入后删空的目录(只删本次新出现且已空的)
  for d in lib/bench_xrchain; do [ -d "$B/$d" ] && rmdir "$B/$d" 2>/dev/null && echo "  删除空目录: $d"; done
  shasum -a 256 -c --quiet $BK/files.sha256 && echo "还原核对: $(wc -l < $BK/list.txt) 个文件哈希一致" || echo "🔴 还原后哈希不一致"
  find . \( -path ./build -o -path ./.dart_tool \) -prune -o -type f -print | sed 's#^\./##' | LC_ALL=C sort > $BK/list_after.txt
  cmp -s $BK/list.txt $BK/list_after.txt && echo "还原核对: 文件清单一致" || echo "🔴 文件清单不一致"
  find . \( -path ./build -o -path ./.dart_tool \) -prune -o -type l -print | sed 's#^\./##' | LC_ALL=C sort | while read l; do printf '%s\t%s\n' "$l" "$(readlink "$l")"; done > $BK/symlinks_after.tsv
  cmp -s $BK/symlinks.tsv $BK/symlinks_after.tsv && echo "还原核对: $(wc -l < $BK/symlinks.tsv) 个符号链接一致" || echo "🔴 符号链接不一致"
  [ "$(readlink $B/pw_full_chain)" = /Users/kaidongwang/.config/superpowers/worktrees/pocketworld/bench-unified-20260924 ] && echo "还原核对: pw_full_chain 指回 bench-unified-20260924" || echo "🔴 pw_full_chain 没指回"
}
trap restore EXIT
# 台架自有文件:本分支快照里改过的 5 份换进来(其余自有文件快照与台架现行版逐字节相同,已核)。
SN=$W/bench/arloopbench_own_snapshot
for f in .sync_from_integration.sh ios/Podfile ios/Runner.xcodeproj/project.pbxproj ios/Runner/Runner-Bridging-Header.h lib/main.dart; do
  cp "$SN/$f" "$B/$f" && cmp -s "$SN/$f" "$B/$f" || { echo "换自有文件失败 $f"; exit 6; }
done
PW_BENCH_SYNC_SOURCE=$W PW_BENCH_FULL_CHAIN_SOURCE=$W PW_BENCH_LIDAR_SOURCE=$W PW_BENCH_UNIFIED_SOURCE=$W PW_BENCH_LOD_VERIFY_ONLY=1 ./.sync_from_integration.sh > $S/logs/sync.log 2>&1 || { echo "同步失败"; tail -8 $S/logs/sync.log; exit 7; }
tail -3 $S/logs/sync.log
need
export LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
( cd ios && PW_XRSLAM_ARM=xrchain pod install > $S/logs/pod_install.log 2>&1 ) || { echo "pod install 失败"; tail -15 $S/logs/pod_install.log; exit 8; }
grep -E "Pod installation complete|PW_XRSLAM" $S/logs/pod_install.log | tail -2
need
export FLUTTER_XCODE_DEBUG_INFORMATION_FORMAT=dwarf FLUTTER_XCODE_LD_GENERATE_MAP_FILE=YES
t0=$(date +%s); PW_XRSLAM_ARM=xrchain flutter build ios --profile --no-pub > $S/logs/build.log 2>&1; rc=$?; echo "构建 rc=$rc 用时 $(( $(date +%s) - t0 )) s"; tail -3 $S/logs/build.log
[ $rc -eq 0 ] || exit 9
$S/tools/verify_build.sh $B/build/ios/iphoneos/Runner.app $BASE > $S/logs/verify_build.txt 2>&1
need
if [ -e $OUT/Runner.app ]; then
  if find /Users/kaidongwang/Developer/arloopbench -maxdepth 5 -type l -print0 | xargs -0 readlink | grep -Fq "$OUT"; then echo "有链接指向旧包,停"; exit 10; fi
  rm -rf $OUT/Runner.app
fi
mkdir -p $OUT; ditto $B/build/ios/iphoneos/Runner.app $OUT/Runner.app
codesign --verify --deep --strict $OUT/Runner.app && echo "复制后签名 valid"
cp $S/logs/verify_build.txt $OUT/verify_build.txt
echo "包: $OUT/Runner.app  源: $(git -C $W log --oneline -1)"
