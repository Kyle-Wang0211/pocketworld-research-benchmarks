// APDe-MVS → WGSL:DepthToWeak(148 行)
// 源:whoiszzj/APDe-MVS(MIT) APD.cu
//
// 作用:判定每个像素是 STRONG / WEAK / UNKNOWN。做法是在**视差域**上
// ±30 档扫代价曲线,数极值点(peak):
//   · 最优 peak 偏离中心太远、或代价 > 0.5      ⇒ WEAK
//   · 只有一个 peak 且代价 ≤ 0.15               ⇒ STRONG(曲线尖锐,匹配唯一)
//   · 多个 peak:其余 peak 与最优的方差 > 0.2   ⇒ STRONG,否则 WEAK
//
// 🔴🔴 性能炸弹(比 FindNearestStrongPoint 更该先量):
//    61 个视差档 × (num_images-1) 个源视图 = **244 次 NCC/像素**(num_images=5)。
//    对照:整个传播三轮才 108 次 NCC/像素。
//    ⇒ **DepthToWeak 单趟 ≈ 传播全程的 2.3 倍。**
//    它还带 61+61 的私有数组(p_costs + is_peak ≈ 305 B/线程)。
//    这是"提速=减少工作量"的头号靶子:视差档数、增量步长都是可调的,
//    而且曲线扫描天然可以粗扫+细化两级。

const D2W_RADIUS : i32 = 30;
const D2W_SIZE   : i32 = 61;   // 2*radius+1

fn depth_to_weak(p : vec2<i32>) -> u32 {
  let width  = i32(P.width);
  let height = i32(P.height);
  let min_margin = 6;
  let center = u32(p.x + p.y * width);

  if (p.x < min_margin || p.y < min_margin
      || p.x >= width - min_margin || p.y >= height - min_margin) {
    return UNKNOWN;
  }

  let sel = selected_views[center];
  let num_images = i32(P.num_images);

  var origin_ph = transform_normal_to_ref_cam(cams[0], plane_hypotheses[center]);
  let origin_depth = origin_ph.w;
  if (origin_depth == 0.0) { return UNKNOWN; }

  var base_line = 0.0;
  var valid_src = 0;
  var weight_normal = 0.0;
  for (var si = 1; si < num_images; si = si + 1) {
    let vi = u32(si - 1);
    if (!is_set(sel, vi)) { continue; }
    weight_normal = weight_normal + vw_get(center, vi);
    let cd = cams[0].c.xyz - cams[si].c.xyz;
    base_line = base_line + sqrt(dot(cd, cd));
    valid_src = valid_src + 1;
  }
  if (valid_src == 0) { return UNKNOWN; }
  base_line = base_line / f32(valid_src);

  let fx = cam_fx(cams[0]);
  let disp = fx * base_line / origin_depth;

  // 🔴 61 档 × 每档 (num_images-1) 次 NCC
  var p_costs : array<f32, 61>;
  for (var i = 0; i < D2W_SIZE; i = i + 1) { p_costs[i] = 2.0; }

  for (var pd = -D2W_RADIUS; pd <= D2W_RADIUS; pd = pd + 1) {
    let p_depth = fx * base_line / (disp + f32(pd));
    if (p_depth < P.depth_min || p_depth > P.depth_max) {
      p_costs[pd + D2W_RADIUS] = 2.0;
      continue;
    }
    var tp = origin_ph;
    tp.w = get_distance_to_origin(cams[0], p, p_depth, tp);
    var p_cost = 0.0;
    for (var si = 1; si < num_images; si = si + 1) {
      let vi = u32(si - 1);
      if (!is_set(sel, vi)) { continue; }
      var tc = compute_bilateral_ncc(p, cams[0], cams[si], tp);
      if (P.geom_consistency == 1u) {
        tc = tc + P.geom_factor * compute_geom_consistency_cost(p, si, tp);
      }
      p_cost = p_cost + tc * vw_get(center, vi);
    }
    p_cost = p_cost / weight_normal;
    p_costs[pd + D2W_RADIUS] = min(2.0, p_cost);
  }

  // ── 找极小值点(原版叫 peak,实际是代价曲线的谷)──────────────
  // ⚠️ 原版循环范围是 [2, size-2),两端各留 2 个不判,照抄。
  var is_peak : array<bool, 61>;
  for (var i = 0; i < D2W_SIZE; i = i + 1) { is_peak[i] = false; }

  var peak_count = 0;
  var min_peak = 0;
  var min_cost = 2.0;
  for (var i = 2; i < D2W_SIZE - 2; i = i + 1) {
    if (p_costs[i - 1] > p_costs[i] && p_costs[i + 1] > p_costs[i]) {
      is_peak[i] = true;
      peak_count = peak_count + 1;
      if (p_costs[i] < min_cost) { min_peak = i; min_cost = p_costs[i]; }
    }
  }

  if (abs(min_peak - D2W_RADIUS) > i32(P.weak_peak_radius) || p_costs[min_peak] > 0.5) {
    return WEAK;
  }

  if (peak_count == 1) {
    if (p_costs[min_peak] <= 0.15) { return STRONG; }
    return WEAK;
  }

  // 多极值:看其余极值与最优的离散度
  var v = 0.0;
  for (var i = 2; i < D2W_SIZE - 2; i = i + 1) {
    if (is_peak[i] && i != min_peak) {
      let d = p_costs[i] - min_cost;
      v = v + d * d;
    }
  }
  v = sqrt(v) / f32(peak_count - 1);

  if (v > 0.2) { return STRONG; }
  return WEAK;
}
