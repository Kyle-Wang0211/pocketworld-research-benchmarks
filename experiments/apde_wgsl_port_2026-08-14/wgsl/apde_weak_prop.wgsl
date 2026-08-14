// APDe-MVS → WGSL:弱纹理传播支
//   ComputeMultiViewCostVectorNew(APD.cu:809)
//   PlaneHypothesisRefinementWeak(APD.cu:1008)
//   CheckerboardPropagationWeak (APD.cu:1442)
// 源:whoiszzj/APDe-MVS(MIT)
//
// 与 Strong 支的三处**结构性**差异(不是笔误,是设计,别照 Strong 抄):
//   ① 邻居不是棋盘 8 向,而是 **GenAnchors 产出的 8 个锚点**,而且要求
//      锚点自身是 STRONG 才算数(APD.cu:1473)。
//   ② 代价一律走 NCCNew(可变形),不走 NCCOld。
//   ③ 精修的第一候选是 RANSACToGetFitPlane 拟合出的平面;**拟合平面为零向量
//      时整个精修直接放弃**(APD.cu:1028 的 return),连随机精修都不做。
//
// 另有两处 Strong/Weak 的条件不同,极易抄串,已逐条核对:
//   · Weak 的几何一致性判据只看 `geom_consistency`,**没有** `use_impetus`
//     (Strong 是 `geom_consistency && use_impetus`)。
//   · Weak 的代价累加带 `if (view_weights[j] > 0)` 守卫,Strong 没有。

// ─── ComputeMultiViewCostVectorNew(APD.cu:809)─────────────────
// 与 Old 版同形:源视图从 1 开始,写进 cost_vector[0..]。
fn compute_multiview_cost_vector_new(p : vec2<i32>, plane : vec4<f32>) -> array<f32, 32> {
  // ⚠️ 调用点都是 `float cost_vector[32] = { 2.0f };` —— C 聚合初始化
  //    只把首元素设成 2.0,其余全 0。照抄。
  var cv : array<f32, 32>;
  cv[0] = 2.0;
  for (var i = 1; i < 32; i = i + 1) { cv[i] = 0.0; }

  for (var i : u32 = 1u; i < P.num_images; i = i + 1u) {
    cv[i - 1u] = compute_bilateral_ncc_new(p, i32(i), plane);
  }
  return cv;
}

// ─── PlaneHypothesisRefinementWeak(APD.cu:1008)────────────────
fn plane_hypothesis_refinement_weak(
  plane_in : vec4<f32>, depth_in : f32, cost_in : f32,
  state : ptr<function, RandState>,
  view_weights : array<f32, 32>, weight_norm : f32,
  p : vec2<i32>
) -> RefineResult {
  let depth_perturbation  = 0.02;
  let normal_perturbation = 0.02;
  let depth_min = P.depth_min;
  let depth_max = P.depth_max;
  let center = u32(p.x + p.y * i32(P.width));

  var plane = plane_in;
  var depth = depth_in;
  var cost  = cost_in;

  var r : RefineResult;

  // ── ① 先试 RANSAC 拟合平面 ──────────────────────────────────
  let fit_plane = fit_plane_hypos[center];
  // ⚠️ 拟合失败(RANSAC 写了 (0,0,0,0))⇒ **整个函数直接返回**,
  //    随机精修那一段根本不执行。这是原版 APD.cu:1028 的 return,
  //    不是 `continue` —— 抄成 continue 会让弱纹理像素多吃一轮随机精修。
  if (fit_plane.x == 0.0 && fit_plane.y == 0.0 && fit_plane.z == 0.0) {
    r.plane = plane; r.depth = depth; r.cost = cost;
    return r;
  }
  {
    let cv = compute_multiview_cost_vector_new(p, fit_plane);
    var temp_cost = 0.0;
    for (var j : u32 = 0u; j < P.num_images - 1u; j = j + 1u) {
      if (view_weights[j] > 0.0) {
        if (P.geom_consistency == 1u) {
          temp_cost = temp_cost + view_weights[j] *
            (cv[j] + P.geom_factor * compute_geom_consistency_cost(p, i32(j) + 1, fit_plane));
        } else {
          temp_cost = temp_cost + view_weights[j] * cv[j];
        }
      }
    }
    temp_cost = temp_cost / weight_norm;

    let depth_before = depth_from_plane(cams[0], fit_plane, p);
    if (depth_before >= depth_min && depth_before <= depth_max && temp_cost < cost) {
      depth = depth_before;
      plane = fit_plane;
      cost  = temp_cost;
    }
  }

  // ── ② 随机精修(5 组候选,与 Strong 同形)────────────────────
  let depth_rand = rand_uniform(state) * (depth_max - depth_min) + depth_min;
  let plane_rand = generate_random_normal(cams[0], p, state, depth);

  // ⚠️ 与 Strong 同一处原版笔误:`while (d < min && d > max)` 恒为假 ⇒
  //    do-while 只跑一次。照抄语义 —— 直接算一次,不循环。
  let dlo = (1.0 - depth_perturbation) * depth;
  let dhi = (1.0 + depth_perturbation) * depth;
  let depth_perturbed = rand_uniform(state) * (dhi - dlo) + dlo;

  let plane_perturbed = generate_perturbed_normal(
      cams[0], p, plane, state, normal_perturbation * 3.14159265358979323846);

  let depths  = array<f32, 5>(depth_rand, depth, depth_rand, depth, depth_perturbed);
  let normals = array<vec4<f32>, 5>(plane, plane_rand, plane_rand, plane_perturbed, plane);

  for (var i = 0; i < 5; i = i + 1) {
    var tp = normals[i];
    tp.w = get_distance_to_origin(cams[0], p, depths[i], tp);
    let cv = compute_multiview_cost_vector_new(p, tp);

    var temp_cost = 0.0;
    for (var j : u32 = 0u; j < P.num_images - 1u; j = j + 1u) {
      if (view_weights[j] > 0.0) {
        if (P.geom_consistency == 1u) {
          temp_cost = temp_cost + view_weights[j] *
            (cv[j] + P.geom_factor * compute_geom_consistency_cost(p, i32(j) + 1, tp));
        } else {
          temp_cost = temp_cost + view_weights[j] * cv[j];
        }
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

  r.plane = plane; r.depth = depth; r.cost = cost;
  return r;
}

// ─── CheckerboardPropagationWeak(APD.cu:1442)──────────────────
// ⚠️ 与 Strong 版不同,这个函数**自己写回**全局(costs / plane_hypotheses /
//    selected_views),不通过返回值 —— 照抄原版的写回时序,因为中间那次
//    `costs[center] = cost_now`(精修**之前**的值)正是末尾 REFINE_INIT
//    比较的基准。抄成"最后统一写回"会改变判据。
//
// 🔴 占用率:cost_array[8][32] = 1KB/线程,和 Strong 版同源同量。
//    加上 view_weights/priors/sampling_probs 各 128B ⇒ 与 Strong 同一量级。
fn checkerboard_propagation_weak(p : vec2<i32>, iter : i32) {
  let width  = i32(P.width);
  let height = i32(P.height);
  let center = p.y * width + p.x;
  let ucenter = u32(center);
  let num_images = i32(P.num_images);

  // ⚠️ `float cost_array[8][32] = { 2.0f }` 的 C 聚合初始化语义:
  //    只有 [0][0] 是 2.0,其余全 0。
  var cost_array : array<array<f32, 32>, 8>;
  for (var d = 0; d < 8; d = d + 1) {
    for (var v = 0; v < 32; v = v + 1) { cost_array[d][v] = 0.0; }
  }
  cost_array[0][0] = 2.0;

  var flag : array<bool, 8>;
  for (var i = 0; i < 8; i = i + 1) { flag[i] = false; }
  var positions : array<i32, 8>;
  for (var i = 0; i < 8; i = i + 1) { positions[i] = 0; }
  var new_plane_hypothesis : array<vec4<f32>, 8>;
  for (var i = 0; i < 8; i = i + 1) { new_plane_hypothesis[i] = vec4<f32>(0.0, 0.0, 0.0, 0.0); }

  // ── Adaptive Checkerboard Sampling:邻居 = 8 个锚点 ─────────
  // ⚠️ 原版这里还累加了 num_valid_pixels,但它**从未被读** —— 死变量,不搬。
  for (var i = 0; i < 8; i = i + 1) {
    let anchor_pt = get_anchor_point(p, u32(i) + 1u);
    if (anchor_pt.x == -1 || anchor_pt.y == -1
        || unpack_weak_info(packed_maps[anchor_pt.x + anchor_pt.y * width]) != STRONG) {
      flag[i] = false;
      continue;
    }
    positions[i] = anchor_pt.x + anchor_pt.y * width;
    flag[i] = true;
    {
      // ⚠️ 同 apde_propagate.wgsl:整行数组赋值会让 spirv-cross 生成签名不匹配
      //    的 spvArrayCopyFromDeviceToStack,MSL 编译失败 ⇒ 逐元素拷贝。
      let cv = compute_multiview_cost_vector_new(p, plane_hypotheses[positions[i]]);
      for (var v = 0; v < 32; v = v + 1) { cost_array[i][v] = cv[v]; }
    }
    new_plane_hypothesis[i] = plane_hypotheses[positions[i]];
  }

  // ── Multi-hypothesis Joint View Selection ───────────────────
  var view_weights : array<f32, 32>;
  for (var i = 0; i < 32; i = i + 1) { view_weights[i] = 0.0; }

  var priors : array<f32, 32>;
  for (var i = 0; i < 32; i = i + 1) { priors[i] = 0.0; }

  // ⚠️ 先验这一轮**不要求**锚点是 STRONG(只要不是 (-1,-1)),
  //    与上面代价那一轮的条件不同。照抄,别合并成一个循环。
  for (var i = 0; i < 8; i = i + 1) {
    let anchor_pt = get_anchor_point(p, u32(i) + 1u);
    if (anchor_pt.x == -1 || anchor_pt.y == -1) { continue; }
    let ac = anchor_pt.x + anchor_pt.y * width;
    for (var j = 0; j < num_images - 1; j = j + 1) {
      if (is_set(selected_views[ac], u32(j))) {
        priors[j] = priors[j] + 0.9;
      } else {
        priors[j] = priors[j] + 0.1;
      }
    }
  }

  var sampling_probs : array<f32, 32>;
  for (var i = 0; i < 32; i = i + 1) { sampling_probs[i] = 0.0; }

  let fi = f32(iter);
  let cost_threshold = 0.8 * exp(fi * fi / (-90.0));
  for (var i = 0; i < num_images - 1; i = i + 1) {
    var count = 0.0;
    var count_false = 0;
    var tmpw = 0.0;
    for (var j = 0; j < 8; j = j + 1) {
      let c = cost_array[j][i];
      if (c < cost_threshold) { tmpw = tmpw + exp(c * c / (-0.18)); count = count + 1.0; }
      if (c > 1.2) { count_false = count_false + 1; }
    }
    if (count > 2.0 && count_false < 3) {
      sampling_probs[i] = tmpw / count;
    } else if (count_false < 3) {
      sampling_probs[i] = exp(cost_threshold * cost_threshold / (-0.32));
    }
    sampling_probs[i] = sampling_probs[i] * priors[i];
  }

  // TransformPDFToCDF(sampling_probs, num_images - 1)
  {
    var prob_sum = 0.0;
    for (var i = 0; i < num_images - 1; i = i + 1) { prob_sum = prob_sum + sampling_probs[i]; }
    let inv = 1.0 / prob_sum;
    var cum = 0.0;
    for (var i = 0; i < num_images - 1; i = i + 1) {
      cum = cum + sampling_probs[i] * inv;
      sampling_probs[i] = cum;
    }
  }

  var st = seed_state(P.rand_seed, ucenter);
  let FLT_EPS = 1.1920929e-7;
  for (var sample = 0; sample < 15; sample = sample + 1) {
    let rand_prob = rand_uniform(&st) - FLT_EPS;
    for (var image_id = 0; image_id < num_images - 1; image_id = image_id + 1) {
      if (sampling_probs[image_id] > rand_prob) {
        view_weights[image_id] = view_weights[image_id] + 1.0;
        break;
      }
    }
  }

  var temp_selected_views = 0u;
  var weight_norm = 0.0;
  // ⚠️ 原版还数了 num_selected_view,同样**从未被读** —— 死变量,不搬。
  for (var i = 0; i < num_images - 1; i = i + 1) {
    if (view_weights[i] > 0.0) {
      temp_selected_views = set_bit(temp_selected_views, u32(i));
      weight_norm = weight_norm + view_weights[i];
    }
  }

  var final_costs : array<f32, 8>;
  for (var i = 0; i < 8; i = i + 1) { final_costs[i] = 0.0; }
  for (var i = 0; i < 8; i = i + 1) {
    var s = 0.0;
    for (var j = 0; j < num_images - 1; j = j + 1) {
      if (view_weights[j] > 0.0) {
        if (P.geom_consistency == 1u) {
          if (flag[i]) {
            s = s + view_weights[j] * (cost_array[i][j] + P.geom_factor *
                  compute_geom_consistency_cost(p, j + 1, plane_hypotheses[positions[i]]));
          } else {
            // ⚠️ 无效方向的几何代价用常数 3.0 顶上(= ComputeGeomConsistencyCost
            //    的 max_cost),不是跳过。照抄。
            s = s + view_weights[j] * (cost_array[i][j] + P.geom_factor * 3.0);
          }
        } else {
          s = s + view_weights[j] * cost_array[i][j];
        }
      }
    }
    final_costs[i] = s / weight_norm;
  }

  let min_cost_idx = find_min_cost_index8(final_costs, 8);

  let plane_center = plane_hypotheses[center];
  let cv_now = compute_multiview_cost_vector_new(p, plane_center);
  var cost_now = 0.0;
  // ⚠️ 这一轮**没有** view_weights[i] > 0 的守卫(与上面那轮不同),照抄。
  for (var i = 0; i < num_images - 1; i = i + 1) {
    if (P.geom_consistency == 1u) {
      cost_now = cost_now + view_weights[i] *
        (cv_now[i] + P.geom_factor * compute_geom_consistency_cost(p, i + 1, plane_center));
    } else {
      cost_now = cost_now + view_weights[i] * cv_now[i];
    }
  }
  cost_now = cost_now / weight_norm;

  // 🔴 这一句的位置是有意义的:末尾 REFINE_INIT 的比较基准就是这里写进去的
  //    **精修前**代价。不要挪到函数末尾。
  costs[center] = cost_now;

  var depth_now = depth_from_plane(cams[0], plane_center, p);
  var plane_now = plane_center;

  if (flag[min_cost_idx]) {
    let depth_before = depth_from_plane(cams[0], new_plane_hypothesis[min_cost_idx], p);
    if (depth_before >= P.depth_min && depth_before <= P.depth_max
        && final_costs[min_cost_idx] < cost_now) {
      depth_now = depth_before;
      plane_now = new_plane_hypothesis[min_cost_idx];
      cost_now  = final_costs[min_cost_idx];
      // 原版这里直接写全局,不经过局部变量
      selected_views[center] = temp_selected_views;
    }
  }

  // view_weights 写回全局(原版是直接在全局上累加的,这里在末尾一次写回;
  // 精修读的是同一份值,行为等价)
  for (var w = 0u; w < 8u; w = w + 1u) {
    var packed = 0u;
    for (var b = 0u; b < 4u; b = b + 1u) {
      let vi = w * 4u + b;
      packed = packed | ((u32(view_weights[vi]) & 0xFFu) << (b * 8u));
    }
    view_weights_buf[ucenter * 8u + w] = packed;
  }

  let r = plane_hypothesis_refinement_weak(
      plane_now, depth_now, cost_now, &st, view_weights, weight_norm, p);
  cost_now  = r.cost;
  plane_now = r.plane;

  if (P.state == STATE_REFINE_INIT) {
    if (cost_now < costs[center] - 0.1) {
      costs[center] = cost_now;
      plane_hypotheses[center] = plane_now;
    }
  } else {
    costs[center] = cost_now;
    plane_hypotheses[center] = plane_now;
  }
}
