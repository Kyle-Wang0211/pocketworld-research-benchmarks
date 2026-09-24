#!/bin/bash
set -u
names=$(curl -sL --max-time 30 "https://fuel.gazebosim.org/1.0/GoogleResearch/models?per_page=100&page=3" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('\n'.join(m['name'] for m in d[::15][:7]))
")
while read -r n; do
  [ -z "$n" ] && continue
  rm -f t.bin
  curl -sL --max-time 40 -H "Range: bytes=0-31" "https://fuel.gazebosim.org/1.0/GoogleResearch/models/$n/tip/files/materials/textures/texture.png" -o t.bin
  python3 - "$n" <<'PY'
import struct,sys,os
n=sys.argv[1]
d=open('t.bin','rb').read() if os.path.exists('t.bin') else b''
if d[:8]==b'\x89PNG\r\n\x1a\n' and len(d)>=24:
    w,h=struct.unpack('>II',d[16:24]); print(f"{n}: {w}x{h}")
else:
    print(f"{n}: NOT PNG ({len(d)} bytes)")
PY
done <<< "$names"
