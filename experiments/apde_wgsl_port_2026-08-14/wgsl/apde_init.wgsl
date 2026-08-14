// APDe-MVS → WGSL:初始化 / 法向变换 / 中值滤波 / 局部精修
// 源:whoiszzj/APDe-MVS(MIT) APD.cu

// ⚠️ 原版局部变量名 filter 在 WGSL 是保留字,统一改名 filt(仅命名)
// ─── sort_small(插入排序,原版逐行)────────────────────────────
fn sort_small21(d : array<f32, 21>, n : i32) -> array<f32, 21> {
  var a = d;
  for (var i = 1; i < n; i = i + 1) {
    let tmp = a[i];
    var j = i;
    loop {
      if (j < 1 || !(tmp < a[j - 1])) { break; }
      a[j] = a[j - 1];
      j = j - 1;
    }
    a[j] = tmp;
  }
  return a;
}

fn sort_small32(d : array<f32, 32>, n : i32) -> array<f32, 32> {
  var a = d;
  for (var i = 1; i < n; i = i + 1) {
    let tmp = a[i];
    var j = i;
    loop {
      if (j < 1 || !(tmp < a[j - 1])) { break; }
      a[j] = a[j - 1];
      j = j - 1;
    }
    a[j] = tmp;
  }
  return a;
}

// ─── TransformNormal / TransformNormal2RefCam ─────────────────
// ⚠️ 两者互为转置:TransformNormal 用 R 的**列**(相机系→世界系),
//    TransformNormal2RefCam 用 R 的**行**(世界系→相机系)。别写反。
fn transform_normal(cam : Camera, ph : vec4<f32>) -> vec4<f32> {
  return vec4<f32>(
    cam.R0.x * ph.x + cam.R1.x * ph.y + cam.R2.x * ph.z,
    cam.R0.y * ph.x + cam.R1.y * ph.y + cam.R2.y * ph.z,
    cam.R0.z * ph.x + cam.R1.z * ph.y + cam.R2.z * ph.z,
    ph.w);
}

fn transform_normal_to_ref_cam(cam : Camera, ph : vec4<f32>) -> vec4<f32> {
  return vec4<f32>(
    dot(cam.R0.xyz, ph.xyz),
    dot(cam.R1.xyz, ph.xyz),
    dot(cam.R2.xyz, ph.xyz),
    ph.w);
}

// ─── GenerateRandomPlaneHypothesis ────────────────────────────
fn generate_random_plane_hypothesis(cam : Camera, p : vec2<i32>,
                                    state : ptr<function, RandState>,
                                    dmin : f32, dmax : f32) -> vec4<f32> {
  let depth = rand_uniform(state) * (dmax - dmin) + dmin;
  var ph = generate_random_normal(cam, p, state, depth);
  ph.w = get_distance_to_origin(cam, p, depth, ph);
  return ph;
}

// ─── ComputeMultiViewInitialCostandSelectedViews ──────────────
// 返回初始代价,并把选中的视图位图写进 selected_views[center]。
// ⚠️ 原版 use_APD && weak_info==WEAK 时走 NCCNew(可变形 NCC),
//    否则走 NCCOld。此处先按 NCCOld 走;NCCNew 见 apde_ncc_new.wgsl。
fn compute_initial_cost_and_views(p : vec2<i32>) -> f32 {
  let center = u32(p.x + p.y * i32(P.width));
  let ph = plane_hypotheses[center];
  let cost_max = 2.0;

  var cv : array<f32, 32>;
  var cv_copy : array<f32, 32>;
  for (var i = 0; i < 32; i = i + 1) { cv[i] = 0.0; cv_copy[i] = 0.0; }
  cv[0] = 2.0; cv_copy[0] = 2.0;   // C 聚合初始化语义

  var cost_count = 0;
  var num_valid_views = 0;
  for (var i : u32 = 1u; i < P.num_images; i = i + 1u) {
    let c = compute_bilateral_ncc(p, cams[0], cams[i], i32(i), ph);
    cv[i - 1u] = c;
    cv_copy[i - 1u] = c;
    cost_count = cost_count + 1;
    if (c < cost_max) { num_valid_views = num_valid_views + 1; }
  }

  cv = sort_small32(cv, cost_count);
  selected_views[center] = 0u;

  let top_k = min(num_valid_views, i32(P.top_k));
  if (top_k > 0) {
    var cost = 0.0;
    for (var i = 0; i < top_k; i = i + 1) { cost = cost + cv[i]; }
    let cost_threshold = cv[top_k - 1];
    var sel = 0u;
    for (var i : u32 = 0u; i < P.num_images - 1u; i = i + 1u) {
      if (cv_copy[i] <= cost_threshold) { sel = set_bit(sel, i); }
    }
    selected_views[center] = sel;
    return cost / f32(top_k);
  }
  return cost_max;
}

// ─── CheckerboardFilterStrong ─────────────────────────────────
// 收集最多 21 个 STRONG 邻居的深度,取中值写回。
// ⚠️ 邻居集合是原版硬编码的 20 个偏移(轴向 ±1/±3/±5 与若干斜向),
//    照抄不化简 —— 它不是规则窗,顺序也影响 index 的填充。
fn checkerboard_filter_strong(p : vec2<i32>) {
  let width  = i32(P.width);
  let height = i32(P.height);
  let center = p.y * width + p.x;
  if (costs[center] < 0.001) { return; }

  var filt : array<f32, 21>;
  for (var i = 0; i < 21; i = i + 1) { filt[i] = 0.0; }
  var index = 0;
  filt[index] = plane_hypotheses[center].w; index = index + 1;

  let left = center - 1;      let leftleft = center - 3;
  let up = center - width;    let upup = center - 3 * width;
  let down = center + width;  let downdown = center + 3 * width;
  let right = center + 1;     let rightright = center + 3;

  // 逐条照抄原版的 20 个条件
  if (p.y > 0 && unpack_weak_info(packed_maps[up]) == STRONG) { filt[index] = plane_hypotheses[up].w; index = index + 1; }
  if (p.y > 2 && unpack_weak_info(packed_maps[upup]) == STRONG) { filt[index] = plane_hypotheses[upup].w; index = index + 1; }
  if (p.y > 4 && unpack_weak_info(packed_maps[upup - width * 2]) == STRONG) { filt[index] = plane_hypotheses[upup - width * 2].w; index = index + 1; }
  if (p.y < height - 1 && unpack_weak_info(packed_maps[down]) == STRONG) { filt[index] = plane_hypotheses[down].w; index = index + 1; }
  if (p.y < height - 3 && unpack_weak_info(packed_maps[downdown]) == STRONG) { filt[index] = plane_hypotheses[downdown].w; index = index + 1; }
  if (p.y < height - 5 && unpack_weak_info(packed_maps[downdown + width * 2]) == STRONG) { filt[index] = plane_hypotheses[downdown + width * 2].w; index = index + 1; }
  if (p.x > 0 && unpack_weak_info(packed_maps[left]) == STRONG) { filt[index] = plane_hypotheses[left].w; index = index + 1; }
  if (p.x > 2 && unpack_weak_info(packed_maps[leftleft]) == STRONG) { filt[index] = plane_hypotheses[leftleft].w; index = index + 1; }
  if (p.x > 4 && unpack_weak_info(packed_maps[leftleft - 2]) == STRONG) { filt[index] = plane_hypotheses[leftleft - 2].w; index = index + 1; }
  if (p.x < width - 1 && unpack_weak_info(packed_maps[right]) == STRONG) { filt[index] = plane_hypotheses[right].w; index = index + 1; }
  if (p.x < width - 3 && unpack_weak_info(packed_maps[rightright]) == STRONG) { filt[index] = plane_hypotheses[rightright].w; index = index + 1; }
  if (p.x < width - 5 && unpack_weak_info(packed_maps[rightright + 2]) == STRONG) { filt[index] = plane_hypotheses[rightright + 2].w; index = index + 1; }
  if (p.y > 0 && p.x < width - 2 && unpack_weak_info(packed_maps[up + 2]) == STRONG) { filt[index] = plane_hypotheses[up + 2].w; index = index + 1; }
  if (p.y < height - 1 && p.x < width - 2 && unpack_weak_info(packed_maps[down + 2]) == STRONG) { filt[index] = plane_hypotheses[down + 2].w; index = index + 1; }
  if (p.y > 0 && p.x > 1 && unpack_weak_info(packed_maps[up - 2]) == STRONG) { filt[index] = plane_hypotheses[up - 2].w; index = index + 1; }
  if (p.y < height - 1 && p.x > 1 && unpack_weak_info(packed_maps[down - 2]) == STRONG) { filt[index] = plane_hypotheses[down - 2].w; index = index + 1; }
  if (p.x > 0 && p.y > 2 && unpack_weak_info(packed_maps[left - width * 2]) == STRONG) { filt[index] = plane_hypotheses[left - width * 2].w; index = index + 1; }
  if (p.x < width - 1 && p.y > 2 && unpack_weak_info(packed_maps[right - width * 2]) == STRONG) { filt[index] = plane_hypotheses[right - width * 2].w; index = index + 1; }
  if (p.x > 0 && p.y < height - 2 && unpack_weak_info(packed_maps[left + width * 2]) == STRONG) { filt[index] = plane_hypotheses[left + width * 2].w; index = index + 1; }
  if (p.x < width - 1 && p.y < height - 2 && unpack_weak_info(packed_maps[right + width * 2]) == STRONG) { filt[index] = plane_hypotheses[right + width * 2].w; index = index + 1; }

  filt = sort_small21(filt, index);
  let mi = index / 2;
  if (index % 2 == 0) {
    plane_hypotheses[center].w = (filt[mi - 1] + filt[mi]) * 0.5;
  } else {
    plane_hypotheses[center].w = filt[mi];
  }
}

// ─── LocalRefine ──────────────────────────────────────────────
// 在**视差域**上 ±5 步搜索更优深度(disp = fx * baseline / depth)。
// 只有改善超过 0.1 才接受。
fn local_refine(p : vec2<i32>) {
  let center = u32(p.x + p.y * i32(P.width));
  let sel = selected_views[center];
  let num_images = i32(P.num_images);

  var origin_ph = transform_normal_to_ref_cam(cams[0], plane_hypotheses[center]);
  let origin_depth = origin_ph.w;
  if (origin_depth == 0.0) { return; }

  var cost_now = 0.0;
  var base_line = 0.0;
  var valid_src = 0;
  var weight_normal = 0.0;
  for (var si = 1; si < num_images; si = si + 1) {
    let vi = u32(si - 1);
    if (!is_set(sel, vi)) { continue; }
    var tp = origin_ph;
    tp.w = get_distance_to_origin(cams[0], p, origin_depth, tp);
    var tc = compute_bilateral_ncc(p, cams[0], cams[si], si, tp);
    if (P.geom_consistency == 1u) {
      tc = tc + P.geom_factor * compute_geom_consistency_cost(p, si, tp);
    }
    let w = vw_get(center, vi);
    cost_now = cost_now + tc * w;
    weight_normal = weight_normal + w;
    let cd = cams[0].c.xyz - cams[si].c.xyz;
    base_line = base_line + sqrt(dot(cd, cd));
    valid_src = valid_src + 1;
  }
  if (weight_normal == 0.0 || valid_src == 0) { return; }

  cost_now = cost_now / weight_normal;
  base_line = base_line / f32(valid_src);

  let fx = cam_fx(cams[0]);
  let disp = fx * base_line / origin_depth;
  var min_cost = 2.0;
  var best_depth = origin_depth;

  for (var pd = -5; pd <= 5; pd = pd + 1) {
    let p_depth = fx * base_line / (disp + f32(pd));
    if (p_depth < P.depth_min || p_depth > P.depth_max) { continue; }
    var tp = origin_ph;
    tp.w = get_distance_to_origin(cams[0], p, p_depth, tp);
    var tc = 0.0;
    for (var si = 1; si < num_images; si = si + 1) {
      let vi = u32(si - 1);
      if (!is_set(sel, vi)) { continue; }
      let w = vw_get(center, vi);
      tc = tc + compute_bilateral_ncc(p, cams[0], cams[si], si, tp) * w;
      if (P.geom_consistency == 1u) {
        tc = tc + P.geom_factor * compute_geom_consistency_cost(p, si, tp) * w;
      }
    }
    tc = tc / weight_normal;
    if (tc < min_cost) { min_cost = tc; best_depth = p_depth; }
  }
  if (cost_now - min_cost > 0.1) {
    plane_hypotheses[center].w = best_depth;
  }
}
