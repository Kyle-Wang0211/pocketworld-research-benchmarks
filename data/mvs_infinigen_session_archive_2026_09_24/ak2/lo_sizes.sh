#!/bin/bash
U=https://docs-assets.developer.apple.com/ml-research/datasets/arkitscenes/v1
one(){ read -r v s <<< "$1"
  a=$(curl -sI --max-time 30 "$U/raw/$s/$v/vga_wide.zip" | tr -d '\r' | awk 'tolower($1)=="content-length:"{print $2}')
  b=$(curl -sI --max-time 30 "$U/raw/$s/$v/lowres_depth.zip" | tr -d '\r' | awk 'tolower($1)=="content-length:"{print $2}')
  echo "$v $s ${a:-0} ${b:-0}"; }
export -f one; export U
xargs -P 24 -I{} bash -c 'one "{}"' < "$1"
