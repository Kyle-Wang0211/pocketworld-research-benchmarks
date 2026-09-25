#!/usr/bin/env bash
# 只读:镜像工作树 vs pw-dense-stage 工作树(跟踪+未跟踪非忽略)逐字节 + 可执行位。
set -euo pipefail
D="$1"; W="$2"; L="$3"; bad=0; n=0
while IFS= read -r f; do
  n=$((n+1))
  cmp -s "$D/$f" "$W/$f" || { echo "DIFF $f"; bad=$((bad+1)); }
  dx=0; wx=0; [ -x "$D/$f" ] && dx=1; [ -x "$W/$f" ] && wx=1
  [ $dx = $wx ] || { echo "MODE $f"; bad=$((bad+1)); }
done < "$L"
echo "compared $n files, mismatches=$bad"
