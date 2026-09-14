#!/bin/bash
# Google Drive 大文件:先拿病毒扫描确认页,解析表单参数再请求
ID=$1; OUT=$2
J=$(mktemp)
H=$(curl -sL -c "$J" "https://drive.google.com/uc?export=download&id=$ID")
ACT=$(echo "$H" | grep -oE 'action="[^"]+"' | head -1 | sed 's/action="//; s/"$//' | sed 's/&amp;/\&/g')
UUID=$(echo "$H" | grep -oE 'name="uuid" value="[^"]+"' | head -1 | sed 's/.*value="//; s/"$//')
CONF=$(echo "$H" | grep -oE 'name="confirm" value="[^"]+"' | head -1 | sed 's/.*value="//; s/"$//')
AT=$(echo "$H" | grep -oE 'name="at" value="[^"]+"' | head -1 | sed 's/.*value="//; s/"$//')
echo "  action=${ACT:0:60}  confirm=$CONF  uuid=${UUID:0:12}"
[ -z "$ACT" ] && { echo "  解析失败"; exit 2; }
curl -sL -b "$J" -o "$OUT" \
  --data-urlencode "id=$ID" --data-urlencode "export=download" \
  --data-urlencode "confirm=$CONF" --data-urlencode "uuid=$UUID" \
  --data-urlencode "at=$AT" -G "$ACT" -w "  HTTP %{http_code}  %{size_download} bytes\n"
rm -f "$J"
file "$OUT" | head -1
