#!/bin/bash
# usage: run_tests.sh <out-file> [extra test files...]
F=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/2359d42b-b338-4098-99ad-6a4c217067ad/scratchpad/fixB
cd $F/dart
out=$1; shift
flutter test $(cat $F/results/touched_tests.txt) "$@" > $out 2>&1
echo "exit=$?" >> $out
tail -2 $out
