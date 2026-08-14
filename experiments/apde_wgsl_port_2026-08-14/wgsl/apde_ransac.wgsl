// APDe-MVS → WGSL:RANSACToGetFitPlane(APD.cu:2486)
// 源:whoiszzj/APDe-MVS(MIT)
//
// 每个 WEAK 像素用自己的 8 个锚点在 **ref 相机系** 里拟合一个平面,
// 结果写进 fit_plane_hypos,供 PlaneHypothesisRefinementWeak 当第一候选。
//
// ⚠️ 与 GenAnchors 里那段 RANSAC **不是同一个** —— 别看到 50 次迭代就复用:
//   | | GenAnchors 里的 | 这里的 |
//   |---|---|---|
//   | 3D 点来源 | plane_hypotheses[.].w **当深度直接用** | 先 ComputeDepthfromPlaneHypothesis **反解**出深度 |
//   | 评分 | 内点计数(阈值 ransac_threshold),平手比中心距离 | 内点距离**求和**取最小,不设阈值 |
//   | 早退 | 无 | min_cost == 0 立即 break |
//   | 法向定向 | 不做 | 做:与视线同向则整体取反(含 .w) |
//   | 用途 | 挑锚点 | 出拟合平面 |
//
// ⚠️ .w 的语义:这个 kernel 跑在传播循环**内部**(APD.cu:2704,夹在
//    Strong 传播与 Weak 传播之间),此时 plane_hypotheses[.].w 还是
//    「到原点距离 d」,不是深度 —— 所以才要 depth_from_plane 反解。
//    别照 ConfidenceCompute/GenAnchors 的口径直接把 .w 当深度。

fn ransac_fit_plane(p : vec2<i32>) {
  let width  = i32(P.width);
  let center = u32(p.x + p.y * width);

  if (unpack_weak_info(packed_maps[center]) != WEAK) {
    fit_plane_hypos[center] = plane_hypotheses[center];
    return;
  }

  let cam = cams[0];
  var st = seed_state(P.rand_seed, center);

  // ANCHOR_NUM - 1 = 8
  var strong_points : array<vec2<i32>, 8>;
  var strong_points_3d : array<vec3<f32>, 8>;
  for (var i = 0; i < 8; i = i + 1) {
    strong_points[i] = vec2<i32>(-1, -1);
    strong_points_3d[i] = vec3<f32>(0.0, 0.0, 0.0);
  }
  var strong_count = 0;

  for (var i : u32 = 1u; i < ANCHOR_NUM; i = i + 1u) {
    let tp = get_anchor_point(p, i);
    if (tp.x == -1 || tp.y == -1) { continue; }
    strong_points[strong_count] = tp;
    let tc = tp.x + tp.y * width;
    // 反解深度:此刻 .w 还是到原点距离 d
    let depth = depth_from_plane(cam, plane_hypotheses[tc], tp);
    strong_points_3d[strong_count] = get_3d_point(cam, tp, depth);
    strong_count = strong_count + 1;
  }

  if (strong_count < 3) {
    fit_plane_hypos[center] = plane_hypotheses[center];
    return;
  }

  var min_cost = 3.4028235e38;          // FLT_MAX
  var best_plane = vec4<f32>(0.0, 0.0, 0.0, 0.0);
  var has_best_plane = false;

  for (var it = 0; it < 50; it = it + 1) {
    let a_index = i32(xorwow_next(&st) % u32(strong_count));
    let b_index = i32(xorwow_next(&st) % u32(strong_count));
    let c_index = i32(xorwow_next(&st) % u32(strong_count));
    if (a_index == b_index || b_index == c_index || a_index == c_index) { continue; }
    if (!point_in_triangle(strong_points[a_index], strong_points[b_index],
                           strong_points[c_index], p)) { continue; }

    let A = strong_points_3d[a_index];
    let B = strong_points_3d[b_index];
    let C = strong_points_3d[c_index];
    let A_C = A - C;
    let B_C = B - C;

    var cross_vec = vec4<f32>(
       A_C.y * B_C.z - B_C.y * A_C.z,
      -(A_C.x * B_C.z - B_C.x * A_C.z),
       A_C.x * B_C.y - B_C.x * A_C.y,
       0.0);
    // isnan:WGSL 没有 isNan(),用 x != x 判(与原版 isnan 同语义)
    if ((cross_vec.x == 0.0 && cross_vec.y == 0.0 && cross_vec.z == 0.0)
        || cross_vec.x != cross_vec.x
        || cross_vec.y != cross_vec.y
        || cross_vec.z != cross_vec.z) { continue; }
    cross_vec = normalize_vec3(cross_vec);
    cross_vec.w = -(cross_vec.x * A.x + cross_vec.y * A.y + cross_vec.z * A.z);

    // ⚠️ 代价是**内点到平面距离之和**(排除三个采样点自身),
    //    不是内点计数 —— 与 GenAnchors 里那段 RANSAC 的判据相反,别抄串。
    var temp_cost = 0.0;
    for (var si = 0; si < strong_count; si = si + 1) {
      if (si == a_index || si == b_index || si == c_index) { continue; }
      let t = strong_points_3d[si];
      temp_cost = temp_cost + abs(cross_vec.x * t.x + cross_vec.y * t.y
                                  + cross_vec.z * t.z + cross_vec.w);
    }
    if (temp_cost < min_cost) {
      min_cost = temp_cost;
      best_plane = cross_vec;
      has_best_plane = true;
    }
    if (min_cost == 0.0) { break; }
  }

  if (has_best_plane) {
    // 定向:法向若与视线同向就整体取反 —— ⚠️ 连 .w 一起取反(原版如此),
    //   这与 GenerateRandomNormal 只翻 xyz 不同,因为那里 .w 还没算。
    let depth = depth_from_plane(cam, plane_hypotheses[center], p);
    let view_direction = get_view_direction(cam, p, depth);
    let dot_product = best_plane.x * view_direction.x
                    + best_plane.y * view_direction.y
                    + best_plane.z * view_direction.z;
    if (dot_product > 0.0) {
      best_plane = vec4<f32>(-best_plane.x, -best_plane.y, -best_plane.z, -best_plane.w);
    }
    fit_plane_hypos[center] = best_plane;
  } else {
    fit_plane_hypos[center] = vec4<f32>(0.0, 0.0, 0.0, 0.0);
  }
}
