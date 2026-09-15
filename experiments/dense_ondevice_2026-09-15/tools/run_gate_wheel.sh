#!/bin/bash
# waits for the wheel reference, then runs the C++ arms and the byte gate against it
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/e8c0e65e-e731-470c-87b9-f01ba7ec3498/scratchpad
REF=$S/fuse_gate/ref_wheel; T=$S/fuse_build/test_fuse
while [ ! -f $REF/summary.json ]; do sleep 15; done
echo "[$(date +%H:%M:%S)] reference ready: $(cat $REF/summary.json)"
run_arm() { # name, extra args
  local name=$1; shift
  local O=$S/fuse_gate/cpp_$name; rm -rf $O; mkdir -p $O
  echo "=== arm $name: $* ==="
  /usr/bin/time -p $T $REF/pack $O "$@" --probe $O/probe 2>&1 | tail -6
  python3.11 $S/fuse_gate_compare.py $REF $O --probe-ref $REF/probe --probe-cpp $O/probe 2>&1
}
run_arm m0_cppinv --mode 0
run_arm m0_inj    --mode 0 --inv-from $REF/pack/inv.f64
run_arm m1_inj    --mode 1 --inv-from $REF/pack/inv.f64
echo GATE_WHEEL_DONE
