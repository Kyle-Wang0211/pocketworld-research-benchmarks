#!/usr/bin/env bash
# 只读:把某个提交的树与某个工作树(跟踪+未跟踪非忽略文件)逐字节对账。
# 用法: verify_tree_vs_worktree.sh <commit> <worktree-dir> <outdir>
# LFS 指针按 oid sha256 对工作树文件内容;其余按 git hash-object --no-filters(纯计算,不写库)。
set -euo pipefail
C="$1"; W="$2"; O="$3"; mkdir -p "$O"
export GIT_OPTIONAL_LOCKS=0
G="git -C $W"
$G ls-tree -r --full-tree "$C" | awk -F'\t' '{split($1,a," "); print a[1]"\t"a[3]"\t"$2}' | LC_ALL=C sort -t$'\t' -k3 > "$O/tree.tsv"
$G ls-files -co --exclude-standard -z | tr '\0' '\n' | LC_ALL=C sort > "$O/wt_files.txt"
cut -f3 "$O/tree.tsv" > "$O/tree_files.txt"
echo "tree files: $(wc -l < "$O/tree_files.txt")  worktree files: $(wc -l < "$O/wt_files.txt")"
comm -23 "$O/tree_files.txt" "$O/wt_files.txt" > "$O/only_in_tree.txt"
comm -13 "$O/tree_files.txt" "$O/wt_files.txt" > "$O/only_in_wt.txt"
# 已跟踪但工作树里被删的文件,ls-files -c 仍会列出,单独查
: > "$O/missing_on_disk.txt"
while IFS= read -r f; do [ -e "$W/$f" ] || [ -L "$W/$f" ] || echo "$f" >> "$O/missing_on_disk.txt"; done < "$O/wt_files.txt"
: > "$O/content_diff.txt"; : > "$O/mode_diff.txt"; n=0; lfs=0
while IFS=$'\t' read -r mode sha path; do
  f="$W/$path"; [ -e "$f" ] || [ -L "$f" ] || continue
  n=$((n+1))
  if [ "$mode" = 120000 ]; then
    t=$(git -C "$W" cat-file -p "$sha"); [ -L "$f" ] && [ "$(readlink "$f")" = "$t" ] || echo "SYMLINK $path" >> "$O/content_diff.txt"; continue
  fi
  if [ -L "$f" ]; then echo "WT_IS_SYMLINK $path" >> "$O/content_diff.txt"; continue; fi
  head=$(git -C "$W" cat-file -p "$sha" | head -c 200 | tr -d '\0' || true)
  if [[ "$head" == "version https://git-lfs.github.com/spec/v1"* ]]; then
    lfs=$((lfs+1))
    oid=$(git -C "$W" cat-file -p "$sha" | sed -n 's/^oid sha256://p')
    got=$(shasum -a 256 "$f" | cut -d' ' -f1)
    [ "$oid" = "$got" ] || echo "LFS $path want=$oid got=$got" >> "$O/content_diff.txt"
  else
    got=$(git hash-object --no-filters -- "$f")
    [ "$got" = "$sha" ] || echo "BLOB $path want=$sha got=$got" >> "$O/content_diff.txt"
  fi
  if [ -x "$f" ]; then m=100755; else m=100644; fi
  [ "$m" = "$mode" ] || echo "MODE $path tree=$mode wt=$m" >> "$O/mode_diff.txt"
done < "$O/tree.tsv"
echo "compared: $n (lfs pointers: $lfs)"
for x in only_in_tree only_in_wt missing_on_disk content_diff mode_diff; do echo "$x: $(wc -l < "$O/$x.txt")"; done
