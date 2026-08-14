// APDe-MVS → WGSL:CheckerboardPropagationStrong(传播主体,343 行)
// 源:whoiszzj/APDe-MVS(MIT) APD.cu
//
// 🔴 占用率警告(移植期就记账,别等上机才发现):
//    原版 `float cost_array[8][32]` = 8 方向 × 32 视图 = **1KB/线程**的
//    lane 私有数组。我们在 A16 的 GPU-TS 战役里已经定罪过:
//    **"A16 占用率真凶 = lane 私有数组"** —— 超出寄存器预算就溢到设备内存,
//    占用率崩掉。这块暂存是自适应棋盘采样天然需要的,搬完必须单独量一次,
//    它可能比 NCC 更早撞墙,而那会改变整个速度结论。
//
//    这里按 num_images 实际值只用前 (num_images-1) 列,但**数组仍按 32 声明**
//    (WGSL 要求编译期常量长度)。真实占用取决于编译器能否证明后面的列没用到。

// 自适应棋盘采样:沿某方向搜索,取代价最小的点。
// 原版把这段在 8 个方向上复制粘贴了 8 遍,结构相同只是边界条件不同。
// ⚠️ 这里做了结构化(用参数表达方向),是移植期的**结构性偏离** ——
//    行为逐点等价,但不是逐行照抄。理由:8 份复制粘贴在 WGSL 里会让
//    函数体超长且极易抄错边界;代价是 parity 对不上时要多查一层。
//    已在 README 的偏离账里登记。

struct PropResult { plane : vec4<f32>, depth : f32, cost : f32, sel_views : u32 };

fn checkerboard_propagation_strong(p : vec2<i32>, iter : i32) -> PropResult {
  let width  = i32(P.width);
  let height = i32(P.height);
  let center = p.y * width + p.x;
  let ucenter = u32(center);
  let num_images = i32(P.num_images);

  // ⚠️ 原版 float cost_array[8][32] = { 2.0f } —— C 聚合初始化只把
  //    **第一个元素**设成 2.0,其余全 0。照抄这个语义。
  var cost_array : array<array<f32, 32>, 8>;
  for (var d = 0; d < 8; d = d + 1) {
    for (var v = 0; v < 32; v = v + 1) { cost_array[d][v] = 0.0; }
  }
  cost_array[0][0] = 2.0;

  var flag : array<bool, 8>;
  for (var i = 0; i < 8; i = i + 1) { flag[i] = false; }

  var positions : array<i32, 8>;
  // 索引约定(照抄原版注释):
  // 0 up_near, 1 up_far, 2 down_near, 3 down_far,
  // 4 left_near, 5 left_far, 6 right_near, 7 right_far
  positions[0] = center - width;
  positions[1] = center - 3 * width;
  positions[2] = center + width;
  positions[3] = center + 3 * width;
  positions[4] = center - 1;
  positions[5] = center - 3;
  positions[6] = center + 1;
  positions[7] = center + 3;

  // ── far 四向:沿轴搜索 11 步(原版 for i in 1..10,步长 2)──────
  // up_far
  if (p.y > 2) {
    flag[1] = true;
    var cmin = costs[positions[1]]; var cpt = positions[1];
    for (var i = 1; i < 11; i = i + 1) {
      if (p.y > 2 + 2 * i) {
        let t = positions[1] - 2 * i * width;
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
    }
    positions[1] = cpt;
    {
      // ⚠️ 不能写成 cost_array[1] = compute_multiview_cost_vector(...):
      //    SPIRV-Cross 对「整个 array<f32,32> 赋值给二维数组的一行」会生成
      //    签名不匹配的 spvArrayCopyFromDeviceToStack,MSL 编译直接失败。
      //    逐元素拷贝,顺带避开整数组拷贝的开销。
      let cv = compute_multiview_cost_vector(p, plane_hypotheses[cpt]);
      for (var v = 0; v < 32; v = v + 1) { cost_array[1][v] = cv[v]; }
    }
  }
  // down_far
  if (p.y < height - 3) {
    flag[3] = true;
    var cmin = costs[positions[3]]; var cpt = positions[3];
    for (var i = 1; i < 11; i = i + 1) {
      if (p.y < height - 3 - 2 * i) {
        let t = positions[3] + 2 * i * width;
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
    }
    positions[3] = cpt;
    {
      // ⚠️ 不能写成 cost_array[3] = compute_multiview_cost_vector(...):
      //    SPIRV-Cross 对「整个 array<f32,32> 赋值给二维数组的一行」会生成
      //    签名不匹配的 spvArrayCopyFromDeviceToStack,MSL 编译直接失败。
      //    逐元素拷贝,顺带避开整数组拷贝的开销。
      let cv = compute_multiview_cost_vector(p, plane_hypotheses[cpt]);
      for (var v = 0; v < 32; v = v + 1) { cost_array[3][v] = cv[v]; }
    }
  }
  // left_far
  if (p.x > 2) {
    flag[5] = true;
    var cmin = costs[positions[5]]; var cpt = positions[5];
    for (var i = 1; i < 11; i = i + 1) {
      if (p.x > 2 + 2 * i) {
        let t = positions[5] - 2 * i;
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
    }
    positions[5] = cpt;
    {
      // ⚠️ 不能写成 cost_array[5] = compute_multiview_cost_vector(...):
      //    SPIRV-Cross 对「整个 array<f32,32> 赋值给二维数组的一行」会生成
      //    签名不匹配的 spvArrayCopyFromDeviceToStack,MSL 编译直接失败。
      //    逐元素拷贝,顺带避开整数组拷贝的开销。
      let cv = compute_multiview_cost_vector(p, plane_hypotheses[cpt]);
      for (var v = 0; v < 32; v = v + 1) { cost_array[5][v] = cv[v]; }
    }
  }
  // right_far
  if (p.x < width - 3) {
    flag[7] = true;
    var cmin = costs[positions[7]]; var cpt = positions[7];
    for (var i = 1; i < 11; i = i + 1) {
      if (p.x < width - 3 - 2 * i) {
        let t = positions[7] + 2 * i;
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
    }
    positions[7] = cpt;
    {
      // ⚠️ 不能写成 cost_array[7] = compute_multiview_cost_vector(...):
      //    SPIRV-Cross 对「整个 array<f32,32> 赋值给二维数组的一行」会生成
      //    签名不匹配的 spvArrayCopyFromDeviceToStack,MSL 编译直接失败。
      //    逐元素拷贝,顺带避开整数组拷贝的开销。
      let cv = compute_multiview_cost_vector(p, plane_hypotheses[cpt]);
      for (var v = 0; v < 32; v = v + 1) { cost_array[7][v] = cv[v]; }
    }
  }

  // ── near 四向:对角搜索 3 步 ─────────────────────────────────
  // up_near
  if (p.y > 0) {
    flag[0] = true;
    var cmin = costs[positions[0]]; var cpt = positions[0];
    for (var i = 0; i < 3; i = i + 1) {
      if (p.y > 1 + i && p.x > i) {
        let t = positions[0] - (1 + i) * width - (i + 1);
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
      if (p.y > 1 + i && p.x < width - 1 - i) {
        let t = positions[0] - (1 + i) * width + (i + 1);
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
    }
    positions[0] = cpt;
    {
      // ⚠️ 不能写成 cost_array[0] = compute_multiview_cost_vector(...):
      //    SPIRV-Cross 对「整个 array<f32,32> 赋值给二维数组的一行」会生成
      //    签名不匹配的 spvArrayCopyFromDeviceToStack,MSL 编译直接失败。
      //    逐元素拷贝,顺带避开整数组拷贝的开销。
      let cv = compute_multiview_cost_vector(p, plane_hypotheses[cpt]);
      for (var v = 0; v < 32; v = v + 1) { cost_array[0][v] = cv[v]; }
    }
  }
  // down_near
  if (p.y < height - 1) {
    flag[2] = true;
    var cmin = costs[positions[2]]; var cpt = positions[2];
    for (var i = 0; i < 3; i = i + 1) {
      if (p.y < height - 2 - i && p.x > i) {
        let t = positions[2] + (1 + i) * width - (i + 1);
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
      if (p.y < height - 2 - i && p.x < width - 1 - i) {
        let t = positions[2] + (1 + i) * width + (i + 1);
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
    }
    positions[2] = cpt;
    {
      // ⚠️ 不能写成 cost_array[2] = compute_multiview_cost_vector(...):
      //    SPIRV-Cross 对「整个 array<f32,32> 赋值给二维数组的一行」会生成
      //    签名不匹配的 spvArrayCopyFromDeviceToStack,MSL 编译直接失败。
      //    逐元素拷贝,顺带避开整数组拷贝的开销。
      let cv = compute_multiview_cost_vector(p, plane_hypotheses[cpt]);
      for (var v = 0; v < 32; v = v + 1) { cost_array[2][v] = cv[v]; }
    }
  }
  // left_near
  if (p.x > 0) {
    flag[4] = true;
    var cmin = costs[positions[4]]; var cpt = positions[4];
    for (var i = 0; i < 3; i = i + 1) {
      if (p.x > 1 + i && p.y > i) {
        let t = positions[4] - (1 + i) - (i + 1) * width;
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
      if (p.x > 1 + i && p.y < height - 1 - i) {
        let t = positions[4] - (1 + i) + (i + 1) * width;
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
    }
    positions[4] = cpt;
    {
      // ⚠️ 不能写成 cost_array[4] = compute_multiview_cost_vector(...):
      //    SPIRV-Cross 对「整个 array<f32,32> 赋值给二维数组的一行」会生成
      //    签名不匹配的 spvArrayCopyFromDeviceToStack,MSL 编译直接失败。
      //    逐元素拷贝,顺带避开整数组拷贝的开销。
      let cv = compute_multiview_cost_vector(p, plane_hypotheses[cpt]);
      for (var v = 0; v < 32; v = v + 1) { cost_array[4][v] = cv[v]; }
    }
  }
  // right_near
  if (p.x < width - 1) {
    flag[6] = true;
    var cmin = costs[positions[6]]; var cpt = positions[6];
    for (var i = 0; i < 3; i = i + 1) {
      if (p.x < width - 2 - i && p.y > i) {
        let t = positions[6] + (1 + i) - (i + 1) * width;
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
      if (p.x < width - 2 - i && p.y < height - 1 - i) {
        let t = positions[6] + (1 + i) + (i + 1) * width;
        if (costs[t] < cmin) { cmin = costs[t]; cpt = t; }
      }
    }
    positions[6] = cpt;
    {
      // ⚠️ 不能写成 cost_array[6] = compute_multiview_cost_vector(...):
      //    SPIRV-Cross 对「整个 array<f32,32> 赋值给二维数组的一行」会生成
      //    签名不匹配的 spvArrayCopyFromDeviceToStack,MSL 编译直接失败。
      //    逐元素拷贝,顺带避开整数组拷贝的开销。
      let cv = compute_multiview_cost_vector(p, plane_hypotheses[cpt]);
      for (var v = 0; v < 32; v = v + 1) { cost_array[6][v] = cv[v]; }
    }
  }

  // ── Multi-hypothesis Joint View Selection ───────────────────
  var view_weights : array<f32, 32>;
  for (var i = 0; i < 32; i = i + 1) { view_weights[i] = 0.0; }

  var priors : array<f32, 32>;
  for (var i = 0; i < 32; i = i + 1) { priors[i] = 0.0; }

  let neighbors = array<i32, 4>(center - width, center + width, center - 1, center + 1);
  for (var i = 0; i < 4; i = i + 1) {
    if (flag[2 * i]) {
      for (var j = 0; j < num_images - 1; j = j + 1) {
        if (is_set(selected_views[neighbors[i]], u32(j))) {
          priors[j] = priors[j] + 0.9;
        } else {
          priors[j] = priors[j] + 0.1;
        }
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

  // TransformPDFToCDF(sampling_probs, num_images - 1) —— 原版只变换前 n 个
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
  // FLT_EPSILON,照抄原版的 -FLT_EPSILON
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
  for (var i = 0; i < num_images - 1; i = i + 1) {
    if (view_weights[i] > 0.0) {
      temp_selected_views = set_bit(temp_selected_views, u32(i));
      weight_norm = weight_norm + view_weights[i];
    }
  }

  var final_costs : array<f32, 8>;
  for (var i = 0; i < 8; i = i + 1) {
    var s = 0.0;
    for (var j = 0; j < num_images - 1; j = j + 1) {
      if (view_weights[j] > 0.0) { s = s + view_weights[j] * cost_array[i][j]; }
    }
    final_costs[i] = s / weight_norm;
  }
  let min_cost_idx = find_min_cost_index8(final_costs, 8);

  // ── 当前假设的代价 ──────────────────────────────────────────
  let plane_center = plane_hypotheses[center];
  let cv_now = compute_multiview_cost_vector(p, plane_center);
  var cost_now = 0.0;
  for (var i = 0; i < num_images - 1; i = i + 1) {
    if (P.geom_consistency == 1u && P.use_impetus == 1u) {
      cost_now = cost_now + view_weights[i] *
        (cv_now[i] + P.geom_factor * compute_geom_consistency_cost(p, i + 1, plane_center));
    } else {
      cost_now = cost_now + view_weights[i] * cv_now[i];
    }
  }
  cost_now = cost_now / weight_norm;

  var depth_now = depth_from_plane(cams[0], plane_center, p);
  var plane_now = plane_center;
  var sel_out = selected_views[center];

  if (flag[min_cost_idx]) {
    let cand = plane_hypotheses[positions[min_cost_idx]];
    let depth_before = depth_from_plane(cams[0], cand, p);
    if (depth_before >= P.depth_min && depth_before <= P.depth_max
        && final_costs[min_cost_idx] < cost_now) {
      depth_now = depth_before;
      plane_now = cand;
      cost_now  = final_costs[min_cost_idx];
      sel_out   = temp_selected_views;
    }
  }

  let r = plane_hypothesis_refinement_strong(
      plane_now, depth_now, cost_now, &st, view_weights, weight_norm, p);

  // 写回 view_weights(打包,给后续 kernel 用)
  for (var w = 0u; w < 8u; w = w + 1u) {
    var packed = 0u;
    for (var b = 0u; b < 4u; b = b + 1u) {
      let vi = w * 4u + b;
      packed = packed | ((u32(view_weights[vi]) & 0xFFu) << (b * 8u));
    }
    view_weights_buf[ucenter * 8u + w] = packed;
  }

  var out : PropResult;
  out.plane = r.plane; out.depth = r.depth; out.cost = r.cost; out.sel_views = sel_out;
  return out;
}
