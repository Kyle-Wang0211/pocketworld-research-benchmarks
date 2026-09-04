#include <metal_stdlib>
#include <metal_simdgroup_matrix>
using namespace metal;

// R2 内层循环:2 行块 × 2 列块 = 4 个 MMA,但每 k 只载入 **2** 个 B fragment。
// 与 k_ilp4 的唯一差异 = B fragment 载入条数 4→2(A 常驻块数 16→32)。
// MMA 条数、store 条数、barrier 条数、tiles 全部相同。
inline void body(device const half* A, threadgroup half* Bsh,
                 threadgroup float* accSh, uint sgid, uint lid, uint tiles) {
  simdgroup_matrix<half, 8, 8> aFrag[16];
  simdgroup_matrix<half, 8, 8> aFrg2[16];
  for (uint k = 0; k < 16u; ++k) {
    simdgroup_load(aFrag[k], A + sgid * 8u * 128u + k * 8u, 128u, ulong2(0, 0));
    simdgroup_load(aFrg2[k], A + (128u + sgid * 8u) * 128u + k * 8u, 128u, ulong2(0, 0));
  }
  for (uint e = lid; e < 4096u; e += 512u) { Bsh[e] = half(e & 7u); }
  threadgroup_barrier(mem_flags::mem_threadgroup);
  for (uint t = 0; t < tiles; ++t) {
    {
      simdgroup_matrix<float, 8, 8> c00 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      simdgroup_matrix<float, 8, 8> c01 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      simdgroup_matrix<float, 8, 8> c10 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      simdgroup_matrix<float, 8, 8> c11 = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      for (uint k = 0; k < 16u; ++k) {
        simdgroup_matrix<half, 8, 8> b0, b1;
        simdgroup_load(b0, Bsh + (0u * 8u) * 128u + k * 8u, 128u, ulong2(0, 0), true);
        simdgroup_load(b1, Bsh + (1u * 8u) * 128u + k * 8u, 128u, ulong2(0, 0), true);
        simdgroup_multiply_accumulate(c00, aFrag[k], b0, c00);
        simdgroup_multiply_accumulate(c01, aFrag[k], b1, c01);
        simdgroup_multiply_accumulate(c10, aFrg2[k], b0, c10);
        simdgroup_multiply_accumulate(c11, aFrg2[k], b1, c11);
      }
      simdgroup_store(c00, accSh + (sgid * 8u) * 32u + 0u * 8u, 32u, ulong2(0, 0));
      simdgroup_store(c01, accSh + (sgid * 8u) * 32u + 1u * 8u, 32u, ulong2(0, 0));
      simdgroup_store(c10, accSh + (sgid * 8u) * 32u + 2u * 8u, 32u, ulong2(0, 0));
      simdgroup_store(c11, accSh + (sgid * 8u) * 32u + 3u * 8u, 32u, ulong2(0, 0));
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
  body(A, Bsh, accSh, sgid, lid, tiles);
  if (lid == 0) out[tg] = accSh[0];
}
