#ifndef NATIVE_BENCH_H
#define NATIVE_BENCH_H
#ifdef __cplusplus
extern "C" {
#endif

// Brute-force SIFT-descriptor matching kernel (128-d L2, nearest + Lowe ratio),
// the core compute of the SfM matching stage. Returns total milliseconds for
// `numPairs` image-pair matches at `numDesc` descriptors each.
//   threads <= 0  -> use all hardware cores
// Pure C++, zero deps -> compiles for iOS arm64 inside the app target, and is
// the same code we'd later call cross-platform via Flutter FFI.
double pw_bench_match(int numDesc, int numPairs, int threads);

// Representative SIFT-extraction cost: builds a Gaussian scale-space pyramid +
// DoG over a synthetic image and samples gradient-histogram descriptors. Not
// bit-exact COLMAP, but a real measure of the device's pyramid+descriptor
// throughput. Returns ms for one image of width x height with `octaves` levels.
double pw_bench_extract(int width, int height, int octaves, int threads);

int pw_num_cores(void);

#ifdef __cplusplus
}
#endif
#endif
