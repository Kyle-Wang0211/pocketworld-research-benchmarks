// APDe-MVS → WGSL:kernel 入口点
// 源:whoiszzj/APDe-MVS(MIT) APD.cu 的 __global__ 函数
//
// 🔴 工具链约束:spirv-cross 每次只出**一个** entry point
//    (官方:"By default, the first entry point in the module is used")
//    ⇒ 多 kernel 必须逐个 `--entry <name> --stage comp`,再一起 metallib 链接。
//    build.sh 已按此处理。
//
// ⚠️ C3:这里的 @workgroup_size 必须与 host 的 threadsPerThreadgroup 一致。
//    目前是手写 16×16 两处,产品化时必须由构建期从 WG_X/WG_Y 生成。

// ─── BlackPixelUpdateStrong / RedPixelUpdateStrong ────────────
// 原版红黑棋盘:黑格 y = 2*ty (+1 当 tx 为奇数);红格相反。
// 照抄 APD.cu:1656-1663 的下标推导。
@compute @workgroup_size(16, 16)
fn black_pixel_update_strong(@builtin(global_invocation_id) g : vec3<u32>) {
  var p = vec2<i32>(i32(g.x), i32(g.y) * 2);
  if ((g.x % 2u) == 1u) { p.y = p.y + 1; }
  if (p.x >= i32(P.width) || p.y >= i32(P.height)) { return; }
  let r = checkerboard_propagation_strong(p, i32(P.iter));
  let c = p.y * i32(P.width) + p.x;
  // 原版按 state 决定是否接受(REFINE_INIT 时要求改善超过 0.1)
  if (P.state == STATE_REFINE_INIT) {
    if (r.cost < costs[c] - 0.1) { costs[c] = r.cost; plane_hypotheses[c] = r.plane; }
  } else {
    costs[c] = r.cost; plane_hypotheses[c] = r.plane;
  }
  selected_views[c] = r.sel_views;
}

@compute @workgroup_size(16, 16)
fn red_pixel_update_strong(@builtin(global_invocation_id) g : vec3<u32>) {
  var p = vec2<i32>(i32(g.x), i32(g.y) * 2);
  if ((g.x % 2u) == 0u) { p.y = p.y + 1; }
  if (p.x >= i32(P.width) || p.y >= i32(P.height)) { return; }
  let r = checkerboard_propagation_strong(p, i32(P.iter));
  let c = p.y * i32(P.width) + p.x;
  if (P.state == STATE_REFINE_INIT) {
    if (r.cost < costs[c] - 0.1) { costs[c] = r.cost; plane_hypotheses[c] = r.plane; }
  } else {
    costs[c] = r.cost; plane_hypotheses[c] = r.plane;
  }
  selected_views[c] = r.sel_views;
}

// ─── ConfidenceCompute ────────────────────────────────────────
@compute @workgroup_size(16, 16)
fn confidence_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  let p = vec2<i32>(i32(g.x), i32(g.y));
  let c = g.y * P.width + g.x;
  let r = confidence_compute(p);
  var m = packed_maps[c];
  if (r == 0xFFFFFFFFu) {
    // ref_depth <= 0 ⇒ weak_info = UNKNOWN,confidence 清零(照抄原版)
    m = (m & 0xFFFF0000u) | UNKNOWN;
  } else {
    m = (m & 0xFFFF00FFu) | ((r & 0xFFu) << 8u);
  }
  packed_maps[c] = m;
}

// ─── FindNearestStrongPoint ───────────────────────────────────
// 🔴 radius=100 ⇒ 每像素 201×201 = 40,401 次。见 apde_weak.wgsl 的性能炸弹说明。
@compute @workgroup_size(16, 16)
fn nearest_strong_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  let q = find_nearest_strong_point(vec2<i32>(i32(g.x), i32(g.y)));
  weak_nearest_buf[g.y * P.width + g.x] =
      (u32(q.y & 0xFFFF) << 16u) | u32(q.x & 0xFFFF);
}

// ─── NCC 打点入口(spike 专用,非算法的一部分)─────────────────
// P.iter 复用为"每像素重复多少次 NCC",用斜率法分离 dispatch 固定开销
// 与单次 NCC 净成本。
@compute @workgroup_size(16, 16)
fn ncc_bench(@builtin(global_invocation_id) gid : vec3<u32>) {
  if (gid.x >= P.width || gid.y >= P.height) { return; }
  let p = vec2<i32>(i32(gid.x), i32(gid.y));
  var acc = 0.0;
  for (var r : u32 = 0u; r < max(P.iter, 1u); r = r + 1u) {
    acc = acc + compute_bilateral_ncc(p, cams[0], cams[1 + (r % 4u)],
                                      vec4<f32>(0.0, 0.0, -1.0, 2.0 + f32(r) * 0.01));
  }
  costs[gid.y * P.width + gid.x] = acc / f32(max(P.iter, 1u));
}
