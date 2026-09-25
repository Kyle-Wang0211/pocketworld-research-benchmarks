#!/bin/bash
# fwcmp.sh SHIP MINE : compare two PWOfficialSfm Mach-O images (unsigned)
SHIP=$1; MINE=$2
echo "size: ship=$(stat -f %z $SHIP) mine=$(stat -f %z $MINE)"
for f in $SHIP $MINE; do segedit $f -extract __TEXT __text /dev/stdout 2>/dev/null | shasum -a 256 | cut -c1-16; done | paste - - | awk '{print "__text sha: ship="$1" mine="$2, ($1==$2?"SAME":"DIFF")}'
diff <(size -m $SHIP | sed 1d) <(size -m $MINE | sed 1d) > /dev/null && echo "section sizes: ALL SAME" || { echo "section sizes: DIFF"; diff <(size -m $SHIP) <(size -m $MINE); }
diff <(nm -gU $SHIP | awk '{print $3}') <(nm -gU $MINE | awk '{print $3}') > /dev/null && echo "exports: SAME ($(nm -gU $MINE | wc -l | tr -d ' '))" || { echo "exports DIFF:"; diff <(nm -gU $SHIP | awk '{print $3}') <(nm -gU $MINE | awk '{print $3}'); }
diff <(nm $SHIP) <(nm $MINE) > /dev/null && echo "full symbol table (addr+type+name): SAME ($(nm $MINE | wc -l | tr -d ' '))" || echo "full symbol table: DIFF $(diff <(nm $SHIP) <(nm $MINE) | grep -c '^[<>]') lines"
for s in "__TEXT __cstring" "__TEXT __const" "__DATA_CONST __const" "__DATA __data"; do
  set -- $s; a=$(segedit $SHIP -extract $1 $2 /dev/stdout 2>/dev/null | shasum -a 256 | cut -c1-12); b=$(segedit $MINE -extract $1 $2 /dev/stdout 2>/dev/null | shasum -a 256 | cut -c1-12); echo "  $1,$2: ship=$a mine=$b $([ $a = $b ] && echo SAME || echo DIFF)"; done
python3 - $SHIP $MINE <<'PY'
import sys
a=open(sys.argv[1],'rb').read(); b=open(sys.argv[2],'rb').read()
b2=b.replace(b'/private/tmp/claude-501/pwfx_aether_cpp',b'/Users/kaidongwang/Developer/aether_cpp')
print('path strings substituted in mine:', b.count(b'/private/tmp/claude-501/pwfx_aether_cpp'))
if len(a)!=len(b2): print('length differs'); sys.exit()
d=[i for i in range(len(a)) if a[i]!=b2[i]]
print('bytes differing after path normalisation:', len(d))
# group runs
runs=[]; 
for i in d:
    if runs and i-runs[-1][1]<=1: runs[-1][1]=i
    else: runs.append([i,i])
for s,e in runs[:12]:
    ctx=slice(max(0,s-24),e+8)
    print(' @0x%x..0x%x ship=%r mine=%r'%(s,e,a[ctx],b2[ctx]))
PY
