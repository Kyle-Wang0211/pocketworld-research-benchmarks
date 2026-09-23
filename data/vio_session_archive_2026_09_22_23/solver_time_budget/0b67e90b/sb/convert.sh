#!/bin/bash
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sb
R=/Users/kaidongwang/Developer/viobench-recordings
T=/Users/kaidongwang/Developer/arloopbench/tools/pwvi_to_euroc.py
/usr/bin/python3 $T $R/run-5966aec0-cbf1-4abc-af0e-c1fc559da44c $S/data/r5966 --intrinsics-csv $S/data/r5966_K.csv > $S/data/r5966.convert.log 2>&1; echo "5966 rc=$?"
/usr/bin/python3 $T $R/run-4ad6e500-ff59-4e67-9bb5-25fb2efe2faa $S/data/r4ad6 --exposure-half --intrinsics-csv $S/data/r4ad6_K.csv > $S/data/r4ad6.convert.log 2>&1; echo "4ad6 rc=$?"
