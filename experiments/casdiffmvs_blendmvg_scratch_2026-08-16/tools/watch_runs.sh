#!/usr/bin/env bash
# 段① 四路训练状态巡检(4 台 vast.ai 上的 RTX 5090)
# ⚠️ 放在研究仓里,别再放 /tmp 或 /private/tmp —— 两处都会被系统清掉。
printf "%-2s %-5s %-7s %-16s %-9s %-8s %-6s %s\n" "" "轮数" "进度" "iter" "lr" "depth" "ckpt" "状态"
for e in "43181:75.152.94.140:A:16" "30901:213.224.31.105:B:24" "42431:71.175.237.103:C:32" "42022:174.119.98.154:D:24"; do
  P=$(echo $e|cut -d: -f1); H=$(echo $e|cut -d: -f2); T=$(echo $e|cut -d: -f3); EP=$(echo $e|cut -d: -f4)
  R=$(ssh -o BatchMode=yes -o ConnectTimeout=20 -p $P root@$H "
    L=/workspace/cfg$T.log
    printf '%s;%s;%s;%s;%s;%s\n' \
      \"\$(grep 'time = ' \$L 2>/dev/null | tail -1 | tr -d '\n')\" \
      \"\$(grep -icE 'nan' \$L 2>/dev/null | tr -d '\n')\" \
      \"\$(grep -icE 'Traceback|out of memory|too old' \$L 2>/dev/null | tr -d '\n')\" \
      \"\$(ls /workspace/runs/*/model_*.ckpt 2>/dev/null | wc -l | tr -d ' \n')\" \
      \"\$(pgrep -f 'train.py' 2>/dev/null | wc -l | tr -d ' \n')\" \
      \"\$(grep -c 'CFG_.*_DONE' \$L 2>/dev/null | tr -d '\n')\"
  " 2>/dev/null)
  IFS=';' read -r last nan err ck alive fin <<< "$R"
  nan=${nan:-0}; err=${err:-0}; ck=${ck:-0}; alive=${alive:-0}; fin=${fin:-0}
  cur=$(echo "$last" | grep -o 'Iter [0-9]*' | grep -o '[0-9]*')
  epn=$(echo "$last" | grep -o 'Epoch [0-9]*' | grep -o '[0-9]*')
  lr=$(echo "$last"  | grep -o 'lr [0-9.]*' | cut -d' ' -f2)
  dep=$(echo "$last" | grep -o 'depth loss = [-0-9.]*' | grep -o '[-0-9.]*$')
  sec=$(echo "$last" | grep -o 'time = [0-9.]*' | grep -o '[0-9.]*$')
  did=$(( ${epn:-0} * 4218 + ${cur:-0} )); tgt=$((EP*4218))
  pct=$(awk -v a="$did" -v b="$tgt" 'BEGIN{printf "%.1f%%", 100*a/b}')
  eta=$(awk -v a="$did" -v b="$tgt" -v s="${sec:-0.45}" 'BEGIN{printf "%.1fh", (b-a)*s/3600}')
  st="✅ 剩 $eta"
  [ "$nan" -gt 0 ] 2>/dev/null && st="🔴 NaN"
  [ "$err" -gt 0 ] 2>/dev/null && st="🔴 ERR"
  [ "$alive" -eq 0 ] 2>/dev/null && { [ "$fin" -gt 0 ] 2>/dev/null && st="🏁 已完成" || st="🔴 进程消失"; }
  printf "%-2s %-5s %-7s %-16s %-9s %-8s %-6s %s\n" "$T" "$EP" "$pct" "${did}/${tgt}" "${lr:-?}" "${dep:-?}" "$ck" "$st"
done
