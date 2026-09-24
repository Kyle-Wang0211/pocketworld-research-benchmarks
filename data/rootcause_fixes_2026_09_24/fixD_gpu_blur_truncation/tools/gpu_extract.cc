// gpu_extract.cc — fixD analysis tool: runs the SHIPPED GPU DSP-SIFT C ABI
// (aether_dsp_sift_extract_gpu_v2, dsp_sift_gpu_c.cc @568f53d3 == shipped
// libpwofficial_gpu_extract.a sources; WGSL byte-identical) on a raw 8-bit gray
// image on the host GPU through Dawn/Metal. Same call shape as the core's
// add_frame (official_aether_sfm_c.cc: max_features, out_cap=max_features).
// Optionally also runs with out_cap large to expose the whole clamp output.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

extern "C" int aether_dsp_sift_extract_gpu_v2(
    const uint8_t* gray, int width, int height, int max_features,
    int num_threads, float* out_xy, uint8_t* out_desc, float* out_scales,
    float* out_orientations, int out_cap, int* out_count);

// CPU fallback symbol required by dsp_sift_gpu_c.cc; the tool must never
// silently use it, so it aborts loudly.
extern "C" int aether_dsp_sift_extract_threaded_v2(
    const uint8_t*, int, int, int, int, float*, uint8_t*, float*, float*, int,
    int*) {
  std::fprintf(stderr, "GPU_EXTRACT: CPU FALLBACK WAS TAKEN\n");
  std::exit(7);
}
extern "C" int aether_dsp_sift_extract_threaded(const uint8_t*, int, int, int,
                                                int, float*, uint8_t*, int,
                                                int*) {
  std::fprintf(stderr, "GPU_EXTRACT: CPU FALLBACK WAS TAKEN\n");
  std::exit(7);
}

int main(int argc, char** argv) {
  if (argc < 7) {
    std::fprintf(stderr, "usage: gray.raw W H max_features out_cap out.bin\n");
    return 2;
  }
  const int W = std::atoi(argv[2]), H = std::atoi(argv[3]);
  const int maxf = std::atoi(argv[4]), cap = std::atoi(argv[5]);
  std::vector<uint8_t> g((size_t)W * H);
  FILE* f = std::fopen(argv[1], "rb");
  if (!f || std::fread(g.data(), 1, g.size(), f) != g.size()) return 3;
  std::fclose(f);
  std::vector<float> xy(2 * (size_t)cap), sc(cap), orr(cap);
  std::vector<uint8_t> desc(128 * (size_t)cap);
  int n = 0;
  const int rc = aether_dsp_sift_extract_gpu_v2(
      g.data(), W, H, maxf, 0, xy.data(), desc.data(), sc.data(), orr.data(),
      cap, &n);
  std::printf("GPU_EXTRACT rc=%d n=%d max_features=%d out_cap=%d\n", rc, n,
              maxf, cap);
  FILE* o = std::fopen(argv[6], "wb");
  std::fwrite(&n, 4, 1, o);
  for (int i = 0; i < n; ++i) {
    float r[4] = {xy[2 * i], xy[2 * i + 1], sc[i], orr[i]};
    std::fwrite(r, 4, 4, o);
  }
  std::fwrite(desc.data(), 1, 128 * (size_t)n, o);
  std::fclose(o);
  return rc;
}
