// APDe-MVS → WGSL:多视图代价向量 + 平面精修
// 源:whoiszzj/APDe-MVS(MIT) APD.cu

// ─── ComputeMultiViewCostVectorOld ────────────────────────────
// 原版:for (i = 1; i < num_images; ++i) cost_vector[i-1] = NCC(p, i, plane)
// ⚠️ 注意索引错位:源视图从 1 开始,写进 cost_vector[0..]
fn compute_multiview_cost_vector(p : vec2<i32>, plane : vec4<f32>) -> array<f32, 32> {
  // ⚠️ 原版是 float cost_vector[32] = { 2.0f };
  //    C 的聚合初始化**只把第一个元素设成 2.0,其余全 0** —— 不是全填 2.0。
  //    照抄这个语义(虽然随后 [0..num_images-2] 都会被覆盖)。
  var cv : array<f32, 32>;
  cv[0] = 2.0;
  for (var i = 1; i < 32; i = i + 1) { cv[i] = 0.0; }

  for (var i : u32 = 1u; i < P.num_images; i = i + 1u) {
    cv[i - 1u] = compute_bilateral_ncc(p, cams[0], cams[i], i32(i), plane);
  }
  return cv;
}

// ─── PlaneHypothesisRefinementStrong ──────────────────────────
// 返回打包的结果:xyz = 法向,w = d;另外用 out 参数式的 struct 带回 depth/cost
struct RefineResult { plane : vec4<f32>, depth : f32, cost : f32 };

fn plane_hypothesis_refinement_strong(
  plane_in : vec4<f32>, depth_in : f32, cost_in : f32,
  state : ptr<function, RandState>,
  view_weights : array<f32, 32>, weight_norm : f32,
  p : vec2<i32>
) -> RefineResult {
  let depth_perturbation  = 0.02;
  let normal_perturbation = 0.02;
  let depth_min = P.depth_min;
  let depth_max = P.depth_max;

  var plane = plane_in;
  var depth = depth_in;
  var cost  = cost_in;

  let depth_rand = rand_uniform(state) * (depth_max - depth_min) + depth_min;
  let plane_rand = generate_random_normal(cams[0], p, state, depth);

  // ⚠️ 原版:
  //      do { depth_perturbed = uniform*(hi-lo)+lo; }
  //      while (depth_perturbed < depth_min && depth_perturbed > depth_max);
  //    这个条件**永远为假**(不可能同时 < min 又 > max),所以循环**恒执行一次**。
  //    这是原版的笔误(大概想写 ||),但照抄语义 ⇒ 这里就是直接算一次,不循环。
  let dlo = (1.0 - depth_perturbation) * depth;
  let dhi = (1.0 + depth_perturbation) * depth;
  let depth_perturbed = rand_uniform(state) * (dhi - dlo) + dlo;

  let plane_perturbed = generate_perturbed_normal(
      cams[0], p, plane, state, normal_perturbation * 3.14159265358979323846);

  // 5 组候选,与原版 depths[]/normals[] 逐位对应
  let depths  = array<f32, 5>(depth_rand, depth, depth_rand, depth, depth_perturbed);
  let normals = array<vec4<f32>, 5>(plane, plane_rand, plane_rand, plane_perturbed, plane);

  for (var i = 0; i < 5; i = i + 1) {
    var tp = normals[i];
    tp.w = get_distance_to_origin(cams[0], p, depths[i], tp);
    let cv = compute_multiview_cost_vector(p, tp);

    var temp_cost = 0.0;
    for (var j : u32 = 0u; j < P.num_images - 1u; j = j + 1u) {
      if (P.geom_consistency == 1u && P.use_impetus == 1u) {
        temp_cost = temp_cost + view_weights[j] *
          (cv[j] + P.geom_factor * compute_geom_consistency_cost(p, i32(j) + 1, tp));
      } else {
        temp_cost = temp_cost + view_weights[j] * cv[j];
      }
    }
    temp_cost = temp_cost / weight_norm;

    let depth_before = depth_from_plane(cams[0], tp, p);
    if (depth_before >= depth_min && depth_before <= depth_max && temp_cost < cost) {
      depth = depth_before;
      plane = tp;
      cost  = temp_cost;
    }
  }

  var r : RefineResult;
  r.plane = plane; r.depth = depth; r.cost = cost;
  return r;
}
