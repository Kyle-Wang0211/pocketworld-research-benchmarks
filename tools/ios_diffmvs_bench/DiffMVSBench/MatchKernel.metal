#include <metal_stdlib>
using namespace metal;

// GPU mirror of pw_bench_match: brute-force 128-d descriptor matching.
// One thread per query descriptor. Each thread scans all `numDesc` db
// descriptors, keeps the two smallest squared-L2 distances (nearest +
// second-nearest), then applies the Lowe ratio test (0.7 -> 0.49 on
// squared distance, matching the CPU kernel's 0.49f * second).
//
// Layout: A (queries) and B (db) are row-major [numDesc][128] floats.
// `out` is one int per query: the matched db index, or -1 if the
// ratio test rejects. The result is consumed only as a sink (timing),
// exactly like the CPU kernel's `sink += bi`.

kernel void pw_match_kernel(device const float *A      [[buffer(0)]],
                            device const float *B      [[buffer(1)]],
                            device int          *out   [[buffer(2)]],
                            constant uint       &numDesc[[buffer(3)]],
                            uint                 gid    [[thread_position_in_grid]])
{
    if (gid >= numDesc) { return; }

    const uint D = 128u;
    device const float *a = A + (uint)gid * D;

    float best   = 1e30f;
    float second = 1e30f;
    int   bi     = -1;

    for (uint j = 0; j < numDesc; ++j) {
        device const float *b = B + j * D;
        float dist = 0.0f;
        // 128-d squared L2, unrolled by the compiler.
        for (uint d = 0; d < D; ++d) {
            float df = a[d] - b[d];
            dist += df * df;
        }
        if (dist < best)        { second = best; best = dist; bi = (int)j; }
        else if (dist < second) { second = dist; }
    }

    // Lowe ratio 0.7 -> 0.7^2 = 0.49 on squared distances.
    out[gid] = (best < 0.49f * second) ? bi : -1;
}
