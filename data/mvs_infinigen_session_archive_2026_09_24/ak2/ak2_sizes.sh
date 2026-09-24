#!/bin/bash
# 逐视频 HEAD 取 wide.zip / highres_depth.zip 的 Content-Length, 用来算批量预算。
U=https://docs-assets.developer.apple.com/ml-research/datasets/arkitscenes/v1
one(){ read -r v s <<< "$1"
  w=$(curl -sI --max-time 30 "$U/raw/$s/$v/wide.zip" | tr -d '\r' | awk 'tolower($1)=="content-length:"{print $2}')
  h=$(curl -sI --max-time 30 "$U/raw/$s/$v/highres_depth.zip" | tr -d '\r' | awk 'tolower($1)=="content-length:"{print $2}')
  echo "$v $s ${w:-0} ${h:-0}"; }
export -f one; export U
xargs -P 24 -I{} bash -c 'one "{}"' < "$1"
