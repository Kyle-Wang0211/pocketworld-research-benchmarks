// fair_match_gen_fixture.cc — constructed parity fixtures for the H2 fair
// matcher harness. Each case attacks a boundary of the fusion / tiling /
// workgroup structure: row and candidate counts straddling workgroup and tile
// sizes, equal-dot ties across workgroups, best==second rejection, single
// candidates, all-zero descriptors, and dots straddling the absolute and
// ratio acos gates.
//
// usage: fair_match_gen_fixture <out_dir> <case>
// cases: r63x129 r65x127 r127x65 r128x129 r129x128 c31 c32 c33 tie_xwg
//        eq_best2 tiny_1x1 tiny_1x2 tiny_2x2 zeros abs_gate ratio_gate\n//        empty_0x64 empty_64x0 empty_0x0

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <string>
#include <vector>

#include "fair_match_common.h"

namespace {

struct Tables {
  std::vector<uint8_t> a, b;
  uint32_t na = 0, nb = 0;
};

uint64_t g_state = 0x9e3779b97f4a7c15ULL;
uint8_t Rnd() {
  g_state ^= g_state << 13;
  g_state ^= g_state >> 7;
  g_state ^= g_state << 17;
  return (uint8_t)(g_state >> 40);
}

// SIFT-shaped random rows: ~25% sparse, rescaled to L2 norm ~505 (just under
// the idealized 512 so dot/512^2 never clamps at 1.0 and the acos gates run
// in their non-degenerate range). A rows are perturbed copies of B rows so
// strong best matches, real second-best distances, and the full ratio /
// absolute gate logic reach the output.
void NormalizeRow(uint8_t* row) {
  double norm2 = 0;
  for (int d = 0; d < 128; ++d) norm2 += (double)row[d] * row[d];
  if (norm2 <= 0) {
    row[0] = 255;
    return;
  }
  const double scale = 505.0 / std::sqrt(norm2);
  for (int d = 0; d < 128; ++d) {
    const int v = (int)(row[d] * scale + 0.5);
    row[d] = (uint8_t)(v > 255 ? 255 : v);
  }
}

Tables Perturbed(uint32_t na, uint32_t nb) {
  Tables t;
  t.na = na;
  t.nb = nb;
  t.b.assign((size_t)nb * 128, 0);
  for (uint32_t j = 0; j < nb; ++j) {
    uint8_t* row = &t.b[(size_t)j * 128];
    for (int d = 0; d < 128; ++d)
      if (Rnd() % 4 == 0) row[d] = Rnd();
    NormalizeRow(row);
  }
  t.a.resize((size_t)na * 128);
  for (uint32_t i = 0; i < na; ++i) {
    uint8_t* row = &t.a[(size_t)i * 128];
    const uint8_t* src = &t.b[(size_t)(i % nb) * 128];
    for (int d = 0; d < 128; ++d) {
      int v = src[d] + (int)(Rnd() % 7) - 3;
      row[d] = (uint8_t)(v < 0 ? 0 : v > 255 ? 255 : v);
    }
    NormalizeRow(row);
  }
  return t;
}

void CopyRow(std::vector<uint8_t>& tbl, uint32_t dst, uint32_t src) {
  std::memcpy(&tbl[(size_t)dst * 128], &tbl[(size_t)src * 128], 128);
}

// Writes an 8/16-dim probe block: base pattern at dims [dim0, dim0+n).
void SetDims(std::vector<uint8_t>& tbl, uint32_t row, uint32_t dim0,
             std::initializer_list<int> vals) {
  uint32_t d = dim0;
  for (int v : vals) tbl[(size_t)row * 128 + d++] = (uint8_t)v;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: %s <out_dir> <case>\n", argv[0]);
    return 1;
  }
  const std::string out_dir = argv[1];
  const std::string name = argv[2];
  Tables t;

  if (name == "r63x129") t = Perturbed(63, 129);
  else if (name == "r65x127") t = Perturbed(65, 127);
  else if (name == "r127x65") t = Perturbed(127, 65);
  else if (name == "r128x129") t = Perturbed(128, 129);
  else if (name == "r129x128") t = Perturbed(129, 128);
  else if (name == "c31") t = Perturbed(64, 31);
  else if (name == "c32") t = Perturbed(64, 32);
  else if (name == "c33") t = Perturbed(64, 33);
  else if (name == "tie_xwg") {
    // Equal-dot ties across workgroup (64-row) and tile (32-col) boundaries:
    // duplicate rows on both sides; strict-> must keep the FIRST index in
    // both the row scan and the ascending column merge.
    t = Perturbed(130, 130);
    CopyRow(t.a, 129, 5);   // column-direction tie: A block 0 vs block 2
    CopyRow(t.b, 125, 7);   // row-direction tie: tile 0 vs tile 3
  } else if (name == "eq_best2") {
    // best == second (identical B rows) must be REJECTED by the >= ratio
    // semantics (bd < ratio*sd fails when bd == sd).
    t = Perturbed(32, 64);
    CopyRow(t.b, 40, 10);
    std::memcpy(&t.a[(size_t)10 * 128], &t.b[(size_t)10 * 128], 128);
  } else if (name == "tiny_1x1" || name == "tiny_1x2" || name == "tiny_2x2") {
    t.na = name == "tiny_2x2" ? 2 : 1;
    t.nb = name == "tiny_1x1" ? 1 : 2;
    t.a.assign((size_t)t.na * 128, 45);  // ~unit SIFT norm: 45^2*128 = 259200
    t.b.assign((size_t)t.nb * 128, 45);
    if (t.nb == 2)
      for (int d = 0; d < 128; ++d) t.b[128 + d] = (uint8_t)(d % 11);
    if (t.na == 2)
      for (int d = 0; d < 128; ++d) t.a[128 + d] = (uint8_t)(d % 11);
  } else if (name == "zeros") {
    t.na = 64;
    t.nb = 64;
    t.a.assign((size_t)t.na * 128, 0);
    t.b.assign((size_t)t.nb * 128, 0);
  } else if (name == "empty_0x64" || name == "empty_64x0" ||
             name == "empty_0x0") {
    // Genuine zero-row tables: exercised at the wrapper layer (the production
    // ABI rejects empty input with rc=1; the portable wrapper early-returns
    // with zero pairs and never hands Dawn a zero-sized buffer).
    t.na = name == "empty_0x64" || name == "empty_0x0" ? 0 : 64;
    t.nb = name == "empty_64x0" || name == "empty_0x0" ? 0 : 64;
    t.a.assign((size_t)t.na * 128, 7);
    t.b.assign((size_t)t.nb * 128, 7);
  } else if (name == "abs_gate") {
    // 16 disjoint 8-dim probes; dot(A_i, B_i) = 200430 + 60 + 2i spans
    // 200490..200520, straddling acos(dot/262144) == 0.7 (~200506).
    t.na = 16;
    t.nb = 16;
    t.a.assign((size_t)16 * 128, 0);
    t.b.assign((size_t)16 * 128, 0);
    for (uint32_t i = 0; i < 16; ++i) {
      SetDims(t.a, i, i * 8, {255, 255, 255, 255, 1, 0, 0, 0});
      SetDims(t.b, i, i * 8, {255, 255, 255, 21, 60 + 2 * (int)i, 0, 0, 0});
    }
  } else if (name == "ratio_gate") {
    // 8 disjoint 16-dim probes, two candidates each: best dot 240000
    // (f32 bd = 0.41397938) and second dot 217605+10i straddling the exact
    // f32 ratio boundary bd == 0.7*sd (between d2 = 217620 and 217630,
    // verified numerically in float32).
    // Mutual holds because each B row's best A partner is A_i.
    t.na = 8;
    t.nb = 16;
    t.a.assign((size_t)8 * 128, 0);
    t.b.assign((size_t)16 * 128, 0);
    for (uint32_t i = 0; i < 8; ++i) {
      SetDims(t.a, i, i * 16, {255, 255, 255, 255, 1});
      SetDims(t.b, 2 * i, i * 16, {255, 255, 255, 176, 45});      // 240000
      SetDims(t.b, 2 * i + 1, i * 16, {255, 255, 255, 88, 90 + 10 * (int)i});
    }
  } else {
    std::fprintf(stderr, "FAIL unknown case %s\n", name.c_str());
    return 1;
  }

  const std::string sha_a = fairmatch::Sha256Hex(t.a.data(), t.a.size());
  const std::string sha_b = fairmatch::Sha256Hex(t.b.data(), t.b.size());
  fairmatch::WriteFileBytes(out_dir + "/a.u8", t.a.data(), t.a.size());
  fairmatch::WriteFileBytes(out_dir + "/b.u8", t.b.data(), t.b.size());
  char manifest[768];
  std::snprintf(manifest, sizeof(manifest),
                "{\n  \"case\": \"%s\",\n  \"rows_a\": %u,\n"
                "  \"sha256_a\": \"%s\",\n  \"rows_b\": %u,\n"
                "  \"sha256_b\": \"%s\",\n  \"cols\": 128,\n"
                "  \"dtype\": \"uint8\"\n}\n",
                name.c_str(), t.na, sha_a.c_str(), t.nb, sha_b.c_str());
  fairmatch::WriteFileBytes(out_dir + "/manifest.json", manifest,
                            std::strlen(manifest));
  std::printf("GEN %s na=%u nb=%u\n", name.c_str(), t.na, t.nb);
  return 0;
}
