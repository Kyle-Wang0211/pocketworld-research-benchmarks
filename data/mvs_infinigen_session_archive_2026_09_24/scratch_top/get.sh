#!/bin/zsh
# usage: get.sh <name> <url>
n=$1; u=$2
curl -sL --retry 3 --max-time 180 -C - -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" "$u" -o "$n.pdf"
ls -la "$n.pdf"
pdftotext "$n.pdf" "$n.txt" 2>/dev/null
wc -l "$n.txt"
