// Thin macOS CLI shell for the LOD bench (correctness runs on the dev machine).
// All engine code is in Sources/lod/pw_lod_bench.cpp; this file only forwards
// argv. No probe on the desktop: thermal/footprint are reported as -1.
//   usage: pwlod_mac <octree_dir> <out_dir> ["key=value key=value ..."]
#include <cstdio>
#include "pw_lod_bench.h"

int main(int argc, char** argv) {
  if (argc < 3) {
    std::fprintf(stderr, "usage: %s <octree_dir> <out_dir> [\"k=v k=v\"]\n", argv[0]);
    return 2;
  }
  const char* r = pwlod_run(argv[1], argv[2], argc > 3 ? argv[3] : "", nullptr, nullptr);
  std::printf("%s\n", r);
  return 0;
}
