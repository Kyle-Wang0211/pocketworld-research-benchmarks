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

// ─── BlackPixelUpdateWeak / RedPixelUpdateWeak(APD.cu:1617/1636)──
// ⚠️ 与 Strong 的两个包装唯一的不同:多一道 `weak_info == WEAK` 的门。
//    下标推导逐字相同。
//
// ⚠️ 原版这两个 kernel 用的 block 是 32×16(BLOCK_W=32, BLOCK_H=16),
//    不是 16×16;而下标只依赖 `threadIdx.x % 2`,两者都是偶数宽度 ⇒
//    用 global_invocation_id.x % 2 等价。host 侧 dispatch 要按
//    (ceil(width/WG_X), ceil((height/2)/WG_Y)) 发,别按全高发。
@compute @workgroup_size(16, 16)
fn black_pixel_update_weak(@builtin(global_invocation_id) g : vec3<u32>) {
  var p = vec2<i32>(i32(g.x), i32(g.y) * 2);
  if ((g.x % 2u) == 1u) { p.y = p.y + 1; }
  if (p.x >= i32(P.width) || p.y >= i32(P.height)) { return; }
  if (unpack_weak_info(packed_maps[u32(p.x + p.y * i32(P.width))]) == WEAK) {
    checkerboard_propagation_weak(p, i32(P.iter));
  }
}

@compute @workgroup_size(16, 16)
fn red_pixel_update_weak(@builtin(global_invocation_id) g : vec3<u32>) {
  var p = vec2<i32>(i32(g.x), i32(g.y) * 2);
  if ((g.x % 2u) == 0u) { p.y = p.y + 1; }
  if (p.x >= i32(P.width) || p.y >= i32(P.height)) { return; }
  if (unpack_weak_info(packed_maps[u32(p.x + p.y * i32(P.width))]) == WEAK) {
    checkerboard_propagation_weak(p, i32(P.iter));
  }
}

// ─── RANSACToGetFitPlane(APD.cu:2486)──────────────────────────
// 跑在传播循环**内部**,每轮 Strong 传播之后、Weak 传播之前。
@compute @workgroup_size(16, 16)
fn ransac_fit_plane_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  ransac_fit_plane(vec2<i32>(i32(g.x), i32(g.y)));
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

// ─── GenAnchors ───────────────────────────────────────────────
// 🔴 私有内存约 1KB+/线程(5 个 32 元素数组)。见 apde_anchors.wgsl 说明。
@compute @workgroup_size(16, 16)
fn gen_anchors_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  let c = g.y * P.width + g.x;
  let reliable = gen_anchors(vec2<i32>(i32(g.x), i32(g.y)));
  // weak_reliable 写进 packed_maps 的第 24..31 位
  packed_maps[c] = (packed_maps[c] & 0x00FFFFFFu) | ((reliable & 0xFFu) << 24u);
}

// ─── RandomInitialization ─────────────────────────────────────
// ⚠️ InitRandomStates 在原版是独立 kernel(curand_init(clock64(),...))。
//    我们改成确定性播种(seed_state),不需要单独的初始化 pass ——
//    每个 kernel 用到时按 (rand_seed, 像素索引) 现场推导,省一个 dispatch
//    和 24 B/px 的常驻状态。这是移植期的合法简化,已登记。
const STATE_FIRST_INIT : u32 = 0u;

@compute @workgroup_size(16, 16)
fn random_init_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  let p = vec2<i32>(i32(g.x), i32(g.y));
  let c = g.y * P.width + g.x;
  var st = seed_state(P.rand_seed, c);
  if (P.state == STATE_FIRST_INIT) {
    plane_hypotheses[c] = generate_random_plane_hypothesis(
        cams[0], p, &st, P.depth_min, P.depth_max);
  } else {
    var ph = transform_normal_to_ref_cam(cams[0], plane_hypotheses[c]);
    let depth = ph.w;
    ph.w = get_distance_to_origin(cams[0], p, depth, ph);
    plane_hypotheses[c] = ph;
  }
  costs[c] = compute_initial_cost_and_views(p);
}

// ─── GetDepthandNormal ────────────────────────────────────────
// 把 plane.w 从「到原点距离 d」改写成「深度」,并把法向转到世界系。
// ⚠️ 这一步之后 .w 的语义变了 —— ConfidenceCompute/GenAnchors 读的就是深度。
@compute @workgroup_size(16, 16)
fn depth_and_normal_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  let p = vec2<i32>(i32(g.x), i32(g.y));
  let c = g.y * P.width + g.x;
  var ph = plane_hypotheses[c];
  ph.w = depth_from_plane(cams[0], ph, p);
  plane_hypotheses[c] = transform_normal(cams[0], ph);
}

// ─── NeigbourUpdate ───────────────────────────────────────────
// WEAK 且 weak_reliable != 1 的降级成 UNKNOWN
@compute @workgroup_size(16, 16)
fn neighbour_update_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  let c = g.y * P.width + g.x;
  let m = packed_maps[c];
  if (unpack_weak_info(m) != WEAK) { return; }
  if (unpack_weak_reliable(m) != 1u) {
    packed_maps[c] = (m & 0xFFFFFF00u) | UNKNOWN;
  }
}

// ─── WeakFilter ───────────────────────────────────────────────
// STRONG 像素若 ±2 邻域内没有其他 STRONG,降级成 UNKNOWN。
// ⚠️ 原版写进 weak_info_copy(另一份缓冲)而不是原地 —— 因为原地会让
//    后来的线程看到已改的值。这里写进 packed_maps 的 weak_reliable 位段
//    当临时通道,由 host 在下一个 pass 里合并。
@compute @workgroup_size(16, 16)
fn weak_filter_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  let width = i32(P.width); let height = i32(P.height);
  let p = vec2<i32>(i32(g.x), i32(g.y));
  let c = g.y * P.width + g.x;
  if (unpack_weak_info(packed_maps[c]) != STRONG) { return; }
  for (var x = -2; x <= 2; x = x + 1) {
    for (var y = -2; y <= 2; y = y + 1) {
      if (x == 0 && y == 0) { continue; }
      let n = vec2<i32>(p.x + x, p.y + y);
      if (n.x < 0 || n.x >= width || n.y < 0 || n.y >= height) { continue; }
      if (unpack_weak_info(packed_maps[u32(n.x + n.y * width)]) == STRONG) { return; }
    }
  }
  // 孤立 STRONG ⇒ 标记待降级(host 在下一 pass 合并成 UNKNOWN)
  packed_maps[c] = (packed_maps[c] & 0x00FFFFFFu) | (0xFEu << 24u);
}

// ─── LocalRefine ──────────────────────────────────────────────
@compute @workgroup_size(16, 16)
fn local_refine_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  local_refine(vec2<i32>(i32(g.x), i32(g.y)));
}

// ─── Black/RedPixelFilterStrong ───────────────────────────────
@compute @workgroup_size(16, 16)
fn black_pixel_filter_strong(@builtin(global_invocation_id) g : vec3<u32>) {
  var p = vec2<i32>(i32(g.x), i32(g.y) * 2);
  if ((g.x % 2u) == 1u) { p.y = p.y + 1; }
  if (p.x >= i32(P.width) || p.y >= i32(P.height)) { return; }
  if (unpack_weak_info(packed_maps[u32(p.x + p.y * i32(P.width))]) != WEAK) {
    checkerboard_filter_strong(p);
  }
}

@compute @workgroup_size(16, 16)
fn red_pixel_filter_strong(@builtin(global_invocation_id) g : vec3<u32>) {
  var p = vec2<i32>(i32(g.x), i32(g.y) * 2);
  if ((g.x % 2u) == 0u) { p.y = p.y + 1; }
  if (p.x >= i32(P.width) || p.y >= i32(P.height)) { return; }
  if (unpack_weak_info(packed_maps[u32(p.x + p.y * i32(P.width))]) != WEAK) {
    checkerboard_filter_strong(p);
  }
}

// ─── DepthToWeak ──────────────────────────────────────────────
// 🔴🔴 244 次 NCC/像素,是全流程最重的单趟。见 apde_depth2weak.wgsl。
@compute @workgroup_size(16, 16)
fn depth_to_weak_kernel(@builtin(global_invocation_id) g : vec3<u32>) {
  if (g.x >= P.width || g.y >= P.height) { return; }
  let c = g.y * P.width + g.x;
  let r = depth_to_weak(vec2<i32>(i32(g.x), i32(g.y)));
  packed_maps[c] = (packed_maps[c] & 0xFFFFFF00u) | r;
}
