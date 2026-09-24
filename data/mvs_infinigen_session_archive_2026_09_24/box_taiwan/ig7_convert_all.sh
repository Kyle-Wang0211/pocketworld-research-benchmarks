#!/bin/bash
# Convert all complete rooms (30 images + 30 depths) into training format under /root/ig7_blend/ig_<seed>.
# Idempotent: skip if pair.txt already exists. Manifest /root/ig7_blend_manifest.tsv records each room's round and recipe.
# Converter = /root/infinigen_to_blend.py (already validated on official layout: reprojection median 0.086 px)
DEST=/root/ig7_blend; MAN=/root/ig7_blend_manifest.tsv; LOG=/root/ig7_convert.log
mkdir -p $DEST; [ -f $MAN ] || printf "scan\tround\trecipe\tstatus\n" > $MAN
conv1(){ d=$1; r=$2; rec=$3; s=$(basename $d)
  [ -f $DEST/ig_$s/cams/pair.txt ] && return 0
  i=$(ls $d/frames/Image/*/Image_*.png 2>/dev/null | wc -l); g=$(ls $d/frames/Depth/*/Depth_*.npy 2>/dev/null | wc -l)
  [ $i -ge 30 ] && [ $g -ge 30 ] || return 0
  if DIFFMVS_DIR=/root/diffmvs_full nice -n 10 /venv/main/bin/python /root/infinigen_to_blend.py --frames $d --out $DEST --scan $s --out_w 768 --out_h 576 --min_frames 8 > /root/ig7_conv_logs/$s.log 2>&1 && [ -f $DEST/ig_$s/cams/pair.txt ]; then
    printf "ig_%s\t%s\t%s\tok\n" $s $r $rec >> $MAN; echo "[$(date +%T)] ok $s ($rec)" >> $LOG
  else printf "ig_%s\t%s\t%s\tFAIL\n" $s $r $rec >> $MAN; echo "[$(date +%T)] FAIL $s" >> $LOG; fi
}
export -f conv1; export DEST MAN LOG; mkdir -p /root/ig7_conv_logs
{ for r in ig7_official ig7_official_b ig7_official_c ig7_official_d; do for d in /root/$r/*/; do echo "${d%/} $r full"; done; done
  for r in ig7_official_e ig7_official_f; do for d in /root/$r/*/; do echo "${d%/} $r fast_solve"; done; done; } | xargs -P 8 -L 1 bash -c 'conv1 "$0" "$1" "$2"'
echo "[$(date +%T)] 本轮转换结束: ok $(grep -c "	ok$" $MAN), FAIL $(grep -c "	FAIL$" $MAN)" >> $LOG
