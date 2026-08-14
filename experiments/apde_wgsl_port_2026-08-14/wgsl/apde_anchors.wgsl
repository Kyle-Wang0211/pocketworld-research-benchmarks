// APDe-MVS → WGSL:GenAnchors(226 行)+ 其辅助函数
// 源:whoiszzj/APDe-MVS(MIT) APD.cu
//
// 这是 APD(Adaptive Patch Deformation)真正的核心:对每个 WEAK 像素,
// 沿 8 个基础方向(每个再旋转 rotate_time 次)向外搜索,找到可靠的 STRONG
// 邻居;再用 RANSAC 在这些邻居的 3D 点上拟合一个平面;最后按到平面的距离
// 排序,取前 8 个当锚点。
//
// 🔴 私有内存(第二块,比传播那 1KB 还散):
//    strong_points[32](vec2<i32> 256B)+ dir_valid[32]
//    + strong_points_valid[32](256B)+ strong_points_valid_3d[32](384B)
//    + weight[32](128B) ≈ **1KB+/线程**。
//    与传播的 cost_array 不在同一个 kernel,但同样要真机复测。
//
// ⚠️ 原版这里用的是 curand()(原始 32 位整数)而非 curand_uniform,
//    并做 `% 2` 与 `% shift_range`。照抄:用 xorwow_next() 取原始值再取模。

// ─── 二维向量helper(对应 NormalizeVec2 / Vec2DotVec2 / Vec2CrossVec2)──
fn normalize_vec2(v : vec2<f32>) -> vec2<f32> {
  return v * inverseSqrt(v.x * v.x + v.y * v.y);
}
fn vec2_dot(a : vec2<f32>, b : vec2<f32>) -> f32 { return a.x * b.x + a.y * b.y; }
fn vec2_cross(a : vec2<f32>, b : vec2<f32>) -> f32 { return a.x * b.y - a.y * b.x; }

// ─── PointinTriangle ──────────────────────────────────────────
// 先查三边长度 > 2 且满足三角不等式,再用叉积同号判内点。
fn point_in_triangle(A : vec2<i32>, B : vec2<i32>, C : vec2<i32>, Pt : vec2<i32>) -> bool {
  let AB = vec2<f32>(f32(B.x - A.x), f32(B.y - A.y));
  let BC = vec2<f32>(f32(C.x - B.x), f32(C.y - B.y));
  let CA = vec2<f32>(f32(A.x - C.x), f32(A.y - C.y));
  let ab = sqrt(AB.x * AB.x + AB.y * AB.y);
  let bc = sqrt(BC.x * BC.x + BC.y * BC.y);
  let ca = sqrt(CA.x * CA.x + CA.y * CA.y);
  if (ab <= 2.0 || bc <= 2.0 || ca <= 2.0) { return false; }
  if (!(ab + bc > ca && bc + ca > ab && ab + ca > bc)) { return false; }
  let PA = vec2<f32>(f32(A.x - Pt.x), f32(A.y - Pt.y));
  let PB = vec2<f32>(f32(B.x - Pt.x), f32(B.y - Pt.y));
  let PC = vec2<f32>(f32(C.x - Pt.x), f32(C.y - Pt.y));
  let t1 = vec2_cross(PA, PB);
  let t2 = vec2_cross(PB, PC);
  let t3 = vec2_cross(PC, PA);
  return t1 * t2 >= 0.0 && t1 * t3 >= 0.0;
}

// ─── GenAnchors ───────────────────────────────────────────────
// 返回 weak_reliable(0/1);锚点直接写进 anchors 缓冲。
fn gen_anchors(p : vec2<i32>) -> u32 {
  let width  = i32(P.width);
  let height = i32(P.height);
  let center = u32(p.x + p.y * width);

  if (unpack_weak_info(packed_maps[center]) != WEAK) { return 0u; }

  let min_margin = 6;
  let depth_diff = P.depth_max - P.depth_min;
  let cam = cams[0];
  let offset = u32(anchors_map[center]) * ANCHOR_NUM;

  var st = seed_state(P.rand_seed, center);

  // 初始化锚点:全 -1,第 0 个是中心点自己
  for (var i : u32 = 0u; i < ANCHOR_NUM; i = i + 1u) {
    anchors_out[offset + i] = 0xFFFFFFFFu;   // (-1,-1) 打包
  }
  anchors_out[offset] = (u32(p.y) << 16u) | u32(p.x);

  var strong_points : array<vec2<i32>, 32>;
  var dir_valid : array<bool, 32>;
  for (var i = 0; i < 32; i = i + 1) {
    strong_points[i] = vec2<i32>(-1, -1);
    dir_valid[i] = false;
  }

  var origin_direction_index = -1;
  var strong_point_size = 0;
  let rotate_time = i32(P.rotate_time);            // 原版 [1,2,4],最大 4
  let angle = 45.0 / f32(rotate_time);
  let PI = 3.14159265358979323846;
  let cos_a = cos(angle * PI / 180.0);
  let sin_a = sin(angle * PI / 180.0);
  let threshhold = cos((angle / 2.0) * PI / 180.0);
  let shift_range = max(i32(tan((angle / 2.0) * PI / 180.0) * 20.0), 1);

  for (var odx = -1; odx <= 1; odx = odx + 1) {
    for (var ody = -1; ody <= 1; ody = ody + 1) {
      if (odx == 0 && ody == 0) { continue; }
      var origin_direction = normalize_vec2(vec2<f32>(f32(odx), f32(ody)));
      origin_direction_index = origin_direction_index + 1;

      for (var rot = 0; rot < rotate_time; rot = rot + 1) {
        let dir_index = origin_direction_index * 4 + rot;

        // ⚠️ 原版 for (radius=2; radius<=MAX_SEARCH_RADIUS;
        //                radius = MIN(radius*2, radius+25))
        //    即先倍增后线性(+25),照抄。MAX_SEARCH_RADIUS = 4096(main.h:42)
        var radius = 2;
        loop {
          if (radius > 4096) { break; }
          let test_pt = vec2<f32>(f32(p.x) + origin_direction.x * f32(radius),
                                  f32(p.y) + origin_direction.y * f32(radius));
          if (test_pt.x < 0.0 || test_pt.y < 0.0
              || test_pt.x >= f32(width) || test_pt.y >= f32(height)) { break; }

          for (var ri = 0; ri < 4; ri = ri + 1) {
            // 照抄原版的取模写法(注意 C 的运算符优先级:
            //   (curand()%2==0 ? 1 : -1) * curand() % shift_range
            // 乘法先于取模 ⇒ 是 (sign*rand) % shift_range,可能为负)
            let sx = select(-1, 1, (xorwow_next(&st) % 2u) == 0u);
            let sy = select(-1, 1, (xorwow_next(&st) % 2u) == 0u);
            let rx = (sx * i32(xorwow_next(&st) & 0x7FFFFFFFu)) % shift_range;
            let ry = (sy * i32(xorwow_next(&st) & 0x7FFFFFFFu)) % shift_range;

            let dir = normalize_vec2(vec2<f32>(origin_direction.x * 20.0 + f32(rx),
                                               origin_direction.y * 20.0 + f32(ry)));
            var apt = vec2<i32>(p.x + i32(dir.x * f32(radius)),
                                p.y + i32(dir.y * f32(radius)));
            if (apt.x < min_margin || apt.y < min_margin
                || apt.x >= width - min_margin || apt.y >= height - min_margin) { continue; }

            // 跳到该点的最近强点
            let packed = weak_nearest_buf[u32(apt.x + apt.y * width)];
            let nx = i32(packed & 0xFFFFu);
            let ny = i32(packed >> 16u);
            // 打包时 -1 存成 0xFFFF
            if (nx == 0xFFFF || ny == 0xFFFF) { continue; }
            apt = vec2<i32>(nx, ny);

            let td = normalize_vec2(vec2<f32>(f32(apt.x - p.x), f32(apt.y - p.y)));
            if (vec2_dot(td, origin_direction) > threshhold) {
              strong_points[dir_index] = apt;
              dir_valid[dir_index] = true;
              strong_point_size = strong_point_size + 1;
              break;
            }
          }
          if (dir_valid[dir_index]) { break; }
          radius = min(radius * 2, radius + 25);
        }

        // 旋转基础方向
        origin_direction = normalize_vec2(vec2<f32>(
            origin_direction.x * cos_a - origin_direction.y * sin_a,
            origin_direction.x * sin_a + origin_direction.y * cos_a));
      }
    }
  }

  if (strong_point_size <= 3) { return 0u; }

  // ── 收集有效强点及其 3D 坐标 ────────────────────────────────
  var sp_valid : array<vec2<i32>, 32>;
  var sp3d : array<vec3<f32>, 32>;
  var valid_count = 0;
  let center_world = get_3d_point(cam, p, plane_hypotheses[center].w);
  for (var i = 0; i < 32; i = i + 1) { sp_valid[i] = vec2<i32>(-1, -1); }
  for (var i = 0; i < 32; i = i + 1) {
    if (dir_valid[i]) {
      let sp = strong_points[i];
      let spc = u32(sp.x + sp.y * width);
      sp_valid[valid_count] = sp;
      sp3d[valid_count] = get_3d_point(cam, sp, plane_hypotheses[spc].w);
      valid_count = valid_count + 1;
    }
  }

  // ── RANSAC 找平面(50 次)────────────────────────────────────
  var best_plane = vec4<f32>(0.0, 0.0, 0.0, 0.0);
  var use_a = -1; var use_b = -1; var use_c = -1;
  var has_valid_plane = false;
  {
    var min_cost = 3.4028235e38;
    var max_count = 3;
    for (var it = 0; it < 50; it = it + 1) {
      let ai = i32(xorwow_next(&st) % u32(valid_count));
      let bi = i32(xorwow_next(&st) % u32(valid_count));
      let ci = i32(xorwow_next(&st) % u32(valid_count));
      if (ai == bi || bi == ci || ai == ci) { continue; }
      if (!point_in_triangle(sp_valid[ai], sp_valid[bi], sp_valid[ci], p)) { continue; }

      let A = sp3d[ai]; let B = sp3d[bi]; let C = sp3d[ci];
      let AC = A - C; let BC = B - C;
      var cv = vec4<f32>(AC.y * BC.z - BC.y * AC.z,
                         -(AC.x * BC.z - BC.x * AC.z),
                         AC.x * BC.y - BC.x * AC.y, 0.0);
      if ((cv.x == 0.0 && cv.y == 0.0 && cv.z == 0.0)
          || cv.x != cv.x || cv.y != cv.y || cv.z != cv.z) { continue; }   // isnan
      cv = normalize_vec3(cv);
      cv.w = -(cv.x * A.x + cv.y * A.y + cv.z * A.z);

      var temp_count = 0;
      for (var si = 0; si < valid_count; si = si + 1) {
        let tp = sp3d[si];
        let d = abs(cv.x * tp.x + cv.y * tp.y + cv.z * tp.z + cv.w);
        if (d / depth_diff < P.ransac_threshold) { temp_count = temp_count + 1; }
      }
      if (temp_count < 6) { continue; }

      let center_distance = abs(cv.x * center_world.x + cv.y * center_world.y
                                + cv.z * center_world.z + cv.w);
      if (temp_count > max_count) {
        max_count = temp_count; min_cost = center_distance;
        best_plane = cv; has_valid_plane = true;
        use_a = ai; use_b = bi; use_c = ci;
      } else if (temp_count == max_count && center_distance < min_cost) {
        min_cost = center_distance;
        best_plane = cv;
        use_a = ai; use_b = bi; use_c = ci;
      }
    }
  }
  if (!has_valid_plane) { return 0u; }

  // ── 按到平面的距离加权排序,取前 8 个当锚点 ──────────────────
  var weight : array<f32, 32>;
  for (var i = 0; i < valid_count; i = i + 1) {
    let tp = sp3d[i];
    var d = abs(best_plane.x * tp.x + best_plane.y * tp.y + best_plane.z * tp.z + best_plane.w);
    if (d / depth_diff >= P.ransac_threshold) {
      sp_valid[i] = vec2<i32>(-1, -1);
      weight[i] = 3.4028235e38;
      continue;
    }
    // 三个采样点自身减 1,保证优先入选(照抄)
    if (i == use_a || i == use_b || i == use_c) { d = d - 1.0; }
    weight[i] = d;
  }

  // sort_small_weighted:插入排序,照抄
  for (var i = 1; i < valid_count; i = i + 1) {
    let tmp = sp_valid[i];
    let tw = weight[i];
    var j = i;
    loop {
      if (j < 1 || !(tw < weight[j - 1])) { break; }
      sp_valid[j] = sp_valid[j - 1];
      weight[j] = weight[j - 1];
      j = j - 1;
    }
    sp_valid[j] = tmp;
    weight[j] = tw;
  }

  for (var i : u32 = 1u; i < ANCHOR_NUM; i = i + 1u) {
    let s = sp_valid[i - 1u];
    if (s.x == -1 || s.y == -1) { continue; }
    anchors_out[offset + i] = (u32(s.y) << 16u) | u32(s.x);
  }
  return 1u;
}
