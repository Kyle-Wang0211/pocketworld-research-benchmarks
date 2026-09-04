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
    for (uint nt = 0; nt < 4u; ++nt) {
      simdgroup_matrix<float, 8, 8> c = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
      for (uint k = 0; k < 16u; ++k) {
        simdgroup_matrix<half, 8, 8> bF;
        simdgroup_load(bF, Bsh + (nt * 8u) * 128u + k * 8u, 128u, ulong2(0, 0), true);
        if (tintForm) {
          simdgroup_matrix<float, 8, 8> d = make_filled_simdgroup_matrix<float, 8, 8>(0.0f);
          simdgroup_multiply_accumulate(d, aFrag[k], bF, c);
          c = d;
        } else {
          simdgroup_multiply_accumulate(c, aFrag[k], bF, c);
        }
      }
      simdgroup_store(c, accSh + (sgid * 8u) * 32u + nt * 8u, 32u, ulong2(0, 0));
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
