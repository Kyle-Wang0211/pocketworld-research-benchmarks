// fair_match_native_arm.mm — H2 harness native arm: the production Metal
// matcher ABI (aether_gpu_match_gemm_pairs) run on one immutable fixture with
// the complete production workload per call (u8->half upload, both search
// directions, in-kernel angular acos ratio + absolute threshold, readback,
// mutual cross-check, deterministic ordered pairs).
//
// usage: fair_match_native_arm <fixture_dir> <out_dir> <reps> <warmup> <ratio>
//
// The production TU official_gpu_match.mm is linked verbatim; env knobs keep
// their production defaults (OFFICIAL_AETHER_MATCH_V2 default on, KNIFE-C
// chunking default on, no thermal duty gap on host because capture is not
// active). Emits per-rep complete wall ms + ordered-pair SHA-256.

#import <Foundation/Foundation.h>

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "fair_match_common.h"

extern "C" int aether_gpu_match_gemm_pairs(const uint8_t*, int, const uint8_t*,
                                           int, double, uint32_t*, int, int*);

namespace {
double NowMs() {
  using namespace std::chrono;
  return duration<double, std::milli>(steady_clock::now().time_since_epoch())
      .count();
}
}  // namespace

int main(int argc, char** argv) {
  if (argc != 6) {
    std::fprintf(stderr,
                 "usage: %s <fixture_dir> <out_dir> <reps> <warmup> <ratio>\n",
                 argv[0]);
    return 1;
  }
  const std::string fixture_dir = argv[1];
  const std::string out_dir = argv[2];
  const int reps = std::atoi(argv[3]);
  const int warmup = std::atoi(argv[4]);
  const double ratio = std::atof(argv[5]);

  const fairmatch::Fixture f = fairmatch::LoadFixture(fixture_dir);

  // Empty-table contract: the production ABI rejects an empty side (rc=1) and
  // the caller (aether_sfm add_frame) never persists matches for it. Verify
  // that fail-closed contract, then emit the wrapper-level result: zero pairs.
  if (f.na == 0 || f.nb == 0) {
    int n = -1;
    const int rc = aether_gpu_match_gemm_pairs(f.a.data(), (int)f.na,
                                               f.b.data(), (int)f.nb, ratio,
                                               nullptr, 0, &n);
    if (rc == 0) {
      std::fprintf(stderr,
                   "FAIL native ABI accepted empty input (rc=0), contract "
                   "expects rejection\n");
      return 22;
    }
    fairmatch::WriteFileBytes(out_dir + "/native_pairs.bin", "", 0);
    std::printf(
        "NATIVE_RESULT {\"arm\":\"native_metal\",\"count\":0,"
        "\"pairs_sha256\":\"%s\",\"empty_input_abi_rc\":%d}\n",
        fairmatch::Sha256Hex("", 0).c_str(), rc);
    return 0;
  }

  const int cap = (int)std::min(f.na, f.nb);
  std::vector<uint32_t> pairs((size_t)cap * 2);

  const char* v2 = getenv("OFFICIAL_AETHER_MATCH_V2");
  std::printf("NATIVE_ARM na=%u nb=%u ratio=%.3f match_v2=%s\n", f.na, f.nb,
              ratio, v2 ? v2 : "(default on)");

  int count = -1;
  auto run_once = [&]() -> int {
    int n = 0;
    const int rc = aether_gpu_match_gemm_pairs(f.a.data(), (int)f.na,
                                               f.b.data(), (int)f.nb, ratio,
                                               pairs.data(), cap, &n);
    if (rc != 0) {
      std::fprintf(stderr, "FAIL native matcher rc=%d\n", rc);
      std::exit(20);
    }
    return n;
  };

  for (int i = 0; i < warmup; ++i) count = run_once();
  std::string digest;
  std::vector<double> wall;
  for (int i = 0; i < reps; ++i) {
    const double t0 = NowMs();
    const int n = run_once();
    const double t1 = NowMs();
    wall.push_back(t1 - t0);
    const std::string d =
        fairmatch::Sha256Hex(pairs.data(), (size_t)n * 2 * sizeof(uint32_t));
    if (i == 0) {
      count = n;
      digest = d;
    } else if (n != count || d != digest) {
      std::fprintf(stderr, "FAIL native output not deterministic across reps\n");
      return 21;
    }
    std::printf("  rep=%d complete_ms=%.3f count=%d\n", i, wall.back(), n);
  }

  fairmatch::WriteFileBytes(out_dir + "/native_pairs.bin", pairs.data(),
                            (size_t)count * 2 * sizeof(uint32_t));
  std::printf(
      "NATIVE_RESULT {\"arm\":\"native_metal\",\"count\":%d,"
      "\"pairs_sha256\":\"%s\",\"wall_ms\":[%s],\"p50_ms\":%.3f,"
      "\"p95_ms\":%.3f}\n",
      count, digest.c_str(), fairmatch::JoinMs(wall).c_str(),
      fairmatch::Percentile(wall, 0.5), fairmatch::Percentile(wall, 0.95));
  return 0;
}
