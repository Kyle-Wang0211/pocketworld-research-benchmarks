#!/bin/zsh
n=$1; u=$2
curl -sL --retry 2 --max-time 150 -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36" "$u" -o "$n.pdf"
pdftotext "$n.pdf" "$n.txt" 2>/dev/null
echo "$n: $(wc -c < $n.pdf 2>/dev/null) bytes pdf, $(wc -l < $n.txt 2>/dev/null) lines txt"
