#!/bin/bash
# 精确量 highres 臂的产出: 只取 lowres_wide.traj + highres_depth.zip 的【中央目录】
# (HTTP Range 取尾部 1 MB, 实测 CDN 返回 206) 就能拿到全部帧时间戳, 不下任何图。
set -u
U=https://docs-assets.developer.apple.com/ml-research/datasets/arkitscenes/v1
D=/root/ak2_hr; mkdir -p "$D"
one(){ read -r v s <<< "$1"
  [ -s "$D/$v.hts" ] && return 0
  [ -s "$D/$v.traj" ] || curl -s --max-time 120 --fail "$U/raw/$s/$v/lowres_wide.traj" -o "$D/$v.traj" || return 1
  curl -s --max-time 180 -r -1048576 "$U/raw/$s/$v/highres_depth.zip" -o "$D/$v.tail" || return 1
  python3 - "$v" <<'PY' > "$D/$v.hts.tmp"
import re,sys,os
v=sys.argv[1]; b=open("/root/ak2_hr/%s.tail"%v,"rb").read()
e=b.rfind(b"PK\x05\x06")
tot=int.from_bytes(b[e+10:e+12],"little") if e>=0 else -1
n=sorted(set(m.group(1).decode() for m in re.finditer(rb"highres_depth/"+v.encode()+rb"_([0-9.]+)\.png",b)))
print("#%d %d"%(tot,len(n)))
print("\n".join(n))
PY
  mv "$D/$v.hts.tmp" "$D/$v.hts"; rm -f "$D/$v.tail"; }
export -f one; export U D
xargs -P 12 -I{} bash -c 'one "{}"' < "$1"
echo "[done] $(ls $D/*.hts 2>/dev/null | wc -l)"
