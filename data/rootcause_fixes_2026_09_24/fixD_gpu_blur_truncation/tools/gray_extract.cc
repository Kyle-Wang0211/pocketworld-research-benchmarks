// gray_extract.cc — run the production CPU DSP-SIFT (aether_dsp_sift_extract_v2) on a raw 8-bit gray file.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
extern "C" int aether_dsp_sift_extract_v2(const uint8_t*, int, int, int, float*, uint8_t*, float*, float*, int, int*);
int main(int argc, char** argv) {
  if (argc < 6) { std::fprintf(stderr, "usage: gray.raw W H max_features out.bin\n"); return 2; }
  const int W = std::atoi(argv[2]), H = std::atoi(argv[3]), maxf = std::atoi(argv[4]);
  std::vector<uint8_t> g((size_t)W * H);
  FILE* f = std::fopen(argv[1], "rb"); std::fread(g.data(), 1, g.size(), f); std::fclose(f);
  const int cap = 400000; int n = 0;
  std::vector<float> xy(2 * (size_t)cap), sc(cap), orr(cap); std::vector<uint8_t> desc(128 * (size_t)cap);
  int rc = aether_dsp_sift_extract_v2(g.data(), W, H, maxf, xy.data(), desc.data(), sc.data(), orr.data(), cap, &n);
  std::printf("GRAY_EXTRACT rc=%d n_full=%d\n", rc, n);
  FILE* o = std::fopen(argv[5], "wb"); std::fwrite(&n, 4, 1, o);
  for (int i = 0; i < n; ++i) { float r[4] = {xy[2*i], xy[2*i+1], sc[i], orr[i]}; std::fwrite(r, 4, 4, o); }
  std::fwrite(desc.data(), 1, 128 * (size_t)n, o); std::fclose(o); return rc;
}
