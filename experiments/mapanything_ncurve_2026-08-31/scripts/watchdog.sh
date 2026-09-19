#!/bin/zsh
while true; do
  P=$(pgrep -f demo_images_only_inference | head -1)
  [ -z "$P" ] && { sleep 1; continue; }
  R=$(ps -o rss= -p $P 2>/dev/null | tr -d ' ')
  [ -n "$R" ] && [ "$R" -gt 14000000 ] && { echo "🔴 看门狗:RSS $((R/1024))MB 超限,杀 $P"; kill -9 $P; }
  sleep 0.5
done
