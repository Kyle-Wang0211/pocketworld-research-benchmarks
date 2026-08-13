// APDe-MVS → WGSL:几何一致性 + 两个小工具
// 源:whoiszzj/APDe-MVS(MIT) APD.cu

// ─── TransformPDFToCDF ────────────────────────────────────────
// CUDA 版原地改写 float* probs。WGSL 没有可变数组参数(C6 同源限制),
// 这里对固定长度 8 的 vector 做,调用点长度就是 8(见 CheckerboardPropagation)。
// ⚠️ 长度写死是移植必需,不是简化 —— 原版调用点也只传 8。
fn transform_pdf_to_cdf8(probs : array<f32, 8>) -> array<f32, 8> {
  var p = probs;
  var prob_sum = 0.0;
  for (var i = 0; i < 8; i = i + 1) { prob_sum = prob_sum + p[i]; }
  let inv = 1.0 / prob_sum;
  var cum = 0.0;
  for (var i = 0; i < 8; i = i + 1) {
    cum = cum + p[i] * inv;
    p[i] = cum;
  }
  return p;
}

// ─── FindMinCostIndex ─────────────────────────────────────────
// ⚠️ 原版用的是 <=(不是 <),相等时取**后面**那个。照抄。
fn find_min_cost_index8(costs : array<f32, 8>, n : i32) -> i32 {
  var min_cost = costs[0];
  var min_idx = 0;
  for (var i = 1; i < n; i = i + 1) {
    if (costs[i] <= min_cost) { min_cost = costs[i]; min_idx = i; }
  }
  return min_idx;
}

fn find_min_cost_index4(costs : array<f32, 4>, n : i32) -> i32 {
  var min_cost = costs[0];
  var min_idx = 0;
  for (var i = 1; i < n; i = i + 1) {
    if (costs[i] <= min_cost) { min_cost = costs[i]; min_idx = i; }
  }
  return min_idx;
}

// ─── ComputeGeomConsistencyCost ───────────────────────────────
// 前向投影到 src 取深度 → 反投回世界 → 投回 ref,量像素级往返误差。
//
// ⚠️ 取样方式与 NCC 不同:原版是 tex2D(depth, (int)x + 0.5f, (int)y + 0.5f)
//    —— **先取整再加 0.5**,即最近邻取像素中心,不是双线性。
//    深度图上做双线性会在深度不连续处造出假值,原版这个选择是对的,照抄。
fn compute_geom_consistency_cost(p : vec2<i32>, src_idx : i32,
                                 plane : vec4<f32>) -> f32 {
  let ref_cam = cams[0];
  let src_cam = cams[src_idx];
  let max_cost = 3.0;

  let depth = depth_from_plane(ref_cam, plane, p);
  let fwd = get_3d_point_on_world(f32(p.x), f32(p.y), depth, ref_cam);

  let sp = project_on_camera(fwd, src_cam);          // (u, v, depth)

  // 最近邻:先截断再取中心
  let sw = f32(src_cam.width); let sh = f32(src_cam.height);
  let su = (floor(sp.x) + 0.5) / sw;
  let sv = (floor(sp.y) + 0.5) / sh;
  let src_depth = textureSampleLevel(depth_tex, samp_nearest,
                                     vec2<f32>(su, sv), src_idx, 0.0).r;

  if (src_depth == 0.0) { return max_cost; }

  let src3d = get_3d_point_on_world(sp.x, sp.y, src_depth, src_cam);
  let bp = project_on_camera(src3d, ref_cam);

  let dx = f32(p.x) - bp.x;
  let dy = f32(p.y) - bp.y;
  return min(max_cost, sqrt(dx * dx + dy * dy));
}
