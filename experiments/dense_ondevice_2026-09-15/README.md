# On-device dense point cloud, 2026-09-15 — scripts, benches and evidence

Companion to `Aether3D-cross/openspec/changes/dense-pointcloud-ondevice-v1/` (proposal / design / contract /
tasks / evidence) and to the C++ in `Aether3D-cross/aether_cpp/src/dense/`. Product wiring lives in the
pocketworld branch `feat/dense-stage` (vendor/pw_dense, lib/dense, viewer). Nothing here is production code.

## What was proven today (all numbers in evidence/stage2-fusion-gate-2026-09-15.md)
- Stage 2 fusion (official cvg/diffmvs filter.py + fuse_official.py) ported to C++ calling the shipped OpenCV 4.0.1
  `cv::remap`: bit-identical to the official Python on fixture97 (22,021,292 points) once the Python cv2 is rebuilt
  with `-ffp-contract=off` (tools/build_cv2_off.sh) — the pip wheel is fp-contract=on and differs by 1 ULP on 21 % of
  interpolated pixels. Same digests on the iPhone 14 Pro (ios_fuse_bench).
- Stage 1 input side: session table (prep_phone_fixture.py port), model inputs (pack_inputs.py port), photos
  (libjpeg-turbo + Pillow Resample.c verbatim) — each byte-identical to the fixture/reference.
- End-to-end on the phone from raw inputs (ios_dense_bench): 26 views @ 2002.6 ms, parity vs PyTorch ✅, fusion
  2,471,620 points (ref 2,471,581); selection box mode: 14 of 97 frames, 81,327 points, 0 outside the box.
- Production (builds 159→162, ledger ~/Developer/pw_builds_20260904/README.md): first real capture (21 photos)
  → 6,922,990 points in 58 s; three incidents fixed the same evening (Stack collapse, unsendable isolate closure,
  Dart-canvas viewer at 6.9 M points → Potree 1 M display budget).

## Layout
- tools/            reference dump, byte comparator, cv2(off) build, host gate builds, sub-pack maker, probes
- ios_fuse_bench/   fusion-only device gate app (com.kyle.casdifffusebench)
- ios_dense_bench/  full-chain device bench (com.kyle.casdiffdensebench), assembly + gated install scripts
- box_parity/       Dart-vs-C++ SelectionBox.contains parity generator and the box used on the device
- logs/             gate logs, device bench results, install gate logs
- evidence/         copy of the OpenSpec evidence file
Paths inside the scripts point at the session scratchpad and local build dirs; they are records, not a re-runnable
package — the C++ sources they compile are in aether_cpp/src/dense.
