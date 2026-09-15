#!/bin/bash
# waits for the fp-contract=off cv2, regenerates the reference with it, runs the production C++ arm, and judges the byte gate
S=/private/tmp/claude-501/-Users-kaidongwang-Documents-progecttwo/e8c0e65e-e731-470c-87b9-f01ba7ec3498/scratchpad
F=/Users/kaidongwang/Documents/progecttwo/_host_experiments.nosync/phone_cap_20260811
PYLIB=$HOME/Developer/opencv-4130-pyoff/pylib
while ! grep -q "CV2OFF_DONE" $S/cv2off_build.log 2>/dev/null; do
  if grep -qE "DOWNLOAD_FAIL|CONFIGURE_FAIL|BUILD_FAIL|INSTALL_FAIL" $S/cv2off_build.log 2>/dev/null; then echo "cv2-off build FAILED"; exit 1; fi
  sleep 30
done
echo "[$(date +%H:%M:%S)] cv2-off ready"
REF=$S/fuse_gate/ref_off; rm -rf $REF
PYTHONPATH=$PYLIB python3.11 $S/fuse_ref_dump.py --fixture $F/fx_official --pred $F/bench_baseline/EXTNF_ABEP2 --out $REF 2>&1 | tail -4
echo "[$(date +%H:%M:%S)] reference(off): $(cat $REF/summary.json)"
T=$S/fuse_build/test_fuse
O=$S/fuse_gate/cpp_off_m0; rm -rf $O; mkdir -p $O
echo "=== production arm: mode 0, C++ lapack_inv, vs ref_off ==="
/usr/bin/time -p $T $REF/pack $O --mode 0 --probe $O/probe --ply $O/fused_cpp.ply 2>&1 | tail -5
python3.11 $S/fuse_gate_compare.py $REF $O --probe-ref $REF/probe --probe-cpp $O/probe 2>&1
echo "=== cross-check: ref_off vs ref_wheel (the FMA-only difference) ==="
python3.11 $S/fuse_gate_compare.py $S/fuse_gate/ref_wheel $REF --probe-ref $S/fuse_gate/ref_wheel/probe --probe-cpp $REF/probe 2>&1 | grep -E "masks|geosum|xyz|sampled|GATE|点数"
echo GATE_OFF_DONE
