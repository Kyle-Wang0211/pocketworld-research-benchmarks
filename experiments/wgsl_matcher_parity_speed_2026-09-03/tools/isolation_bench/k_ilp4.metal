#include <metal_stdlib>
#include <metal_simdgroup_matrix>
using namespace metal;

// 复刻现役内层循环的形状:16 个 aFrag 常驻,每块 4 个 nt × 16 个 k 的 MMA。
// FORM_A = 手写 Metal 形态(原地累加,dst == src)
// FORM_B = tint 生成形态(独立 dst + 零填充 + 整块拷回)
template <bool tintForm>
inline void body(device const half* A, threadgroup half* Bsh,
                 threadgroup float* accSh, uint sgid, uint lid, uint tiles) {
  simdgroup_matrix<half, 8, 8> aFrag[16];
  for (uint k = 0; k < 16u; ++k) {
    simdgroup_load(aFrag[k], A + sgid * 8u * 128u + k * 8u, 128u, ulong2(0, 0));
  }
  for (uint e = lid; e < 4096u; e += 512u) { Bsh[e] = half(e & 7u); }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  for (uint t = 0; t < tiles; ++t) {
    {
      simdgroup_matrix<float, 8, 8> c0 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      simdgroup_matrix<float, 8, 8> c1 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      simdgroup_matrix<float, 8, 8> c2 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      simdgroup_matrix<float, 8, 8> c3 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      for (uint k = 0; k < 16u; ++k) {
        simdgroup_matrix<half, 8, 8> b0, b1, b2, b3;
        simdgroup_load(b0, Bsh + (0u * 8u) * 128u + k * 8u, 128u, ulong2(0, 0), true);
        simdgroup_load(b1, Bsh + (1u * 8u) * 128u + k * 8u, 128u, ulong2(0, 0), true);
        simdgroup_load(b2, Bsh + (2u * 8u) * 128u + k * 8u, 128u, ulong2(0, 0), true);
        simdgroup_load(b3, Bsh + (3u * 8u) * 128u + k * 8u, 128u, ulong2(0, 0), true);
        simdgroup_multiply_accumulate(c0, aFrag[k], b0, c0);
        simdgroup_multiply_accumulate(c1, aFrag[k], b1, c1);
        simdgroup_multiply_accumulate(c2, aFrag[k], b2, c2);
        simdgroup_multiply_accumulate(c3, aFrag[k], b3, c3);
      }
      simdgroup_store(c0, accSh + (sgid * 8u) * 32u + 0u * 8u, 32u, ulong2(0, 0));
      simdgroup_store(c1, accSh + (sgid * 8u) * 32u + 1u * 8u, 32u, ulong2(0, 0));
      simdgroup_store(c2, accSh + (sgid * 8u) * 32u + 2u * 8u, 32u, ulong2(0, 0));
      simdgroup_store(c3, accSh + (sgid * 8u) * 32u + 3u * 8u, 32u, ulong2(0, 0));
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    threadgroup_barrier(mem_flags::mem_threadgroup);
  }
}

kernel void formA(device const half* A [[buffer(0)]], device float* out [[buffer(1)]],
                  constant uint& tiles [[buffer(2)]],
                  threadgroup half* Bsh [[threadgroup(0)]],
                  threadgroup float* accSh [[threadgroup(1)]],
                  uint lid [[thread_index_in_threadgroup]],
                  uint sgid [[simdgroup_index_in_threadgroup]],
                  uint tg [[threadgroup_position_in_grid]]) {
  body<false>(A, Bsh, accSh, sgid, lid, tiles);
  if (lid == 0) out[tg] = accSh[0];
}
kernel void formB(device const half* A [[buffer(0)]], device float* out [[buffer(1)]],
                  constant uint& tiles [[buffer(2)]],
                  threadgroup half* Bsh [[threadgroup(0)]],
                  threadgroup float* accSh [[threadgroup(1)]],
                  uint lid [[thread_index_in_threadgroup]],
                  uint sgid [[simdgroup_index_in_threadgroup]],
                  uint tg [[threadgroup_position_in_grid]]) {
  body<true>(A, Bsh, accSh, sgid, lid, tiles);
  if (lid == 0) out[tg] = accSh[0];
}
