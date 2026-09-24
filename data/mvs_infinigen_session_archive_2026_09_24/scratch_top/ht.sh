#!/bin/zsh
n=$1; u=$2
curl -sL --retry 2 --max-time 90 -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36" "$u" -o "$n.html"
python3 - "$n" <<'PY'
import sys,re,html
n=sys.argv[1]
s=open(n+'.html',encoding='utf-8',errors='replace').read()
s=re.sub(r'(?is)<(script|style|nav|footer)[^>]*>.*?</\1>',' ',s)
s=re.sub(r'(?s)<[^>]+>',' ',s)
s=html.unescape(s)
s=re.sub(r'[ \t]+',' ',s)
s=re.sub(r'\n\s*\n+','\n',s)
open(n+'.txt','w',encoding='utf-8').write(s)
print(n, len(s))
PY
