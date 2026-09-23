#!/bin/bash
set -uo pipefail
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/0b67e90b-a648-4571-8c8b-efe50b991a36/scratchpad/sb
export PW_CMAKE_STUBS=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/4437f552-36d8-4d91-9d8d-ae4aaadf54b6/scratchpad/stubs
export JOBS=10
echo "== base $(date)"
bash $S/base-04c0e83/pw_tools/regression/build_pc_headless.sh $S/base-04c0e83 $S/build-base 2>&1 | tail -5
echo "== branch $(date)"
W=/Users/kaidongwang/Developer/xrslam-wt/solver-budget
bash $W/pw_tools/regression/build_pc_headless.sh $W $S/build-branch 2>&1 | tail -5
echo "== done $(date)"
