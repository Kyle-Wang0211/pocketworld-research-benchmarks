// APDe-MVS → WGSL:弱纹理链(置信度 / 最近强点)
// 源:whoiszzj/APDe-MVS(MIT) APD.cu
//
// 🔴 性能炸弹(移植期记账):FindNearestStrongPoint 的 radius = 100,
//    即每像素扫 201×201 = 40,401 个邻居。896×512 下是 **185 亿次迭代**,
//    这一个 kernel 就可能盖过 NCC + 传播的总和。
//    照抄不改,但上机第一件事就是单独量它 —— 它很可能是真正的瓶颈,
//    而且它是 O(radius²) 的暴力搜索,有明显的算法级优化空间(跳跃搜索 /
//    分离轴 / 距离变换),那是"提速=减少工作量"的合法目标。

// weak_info 的三态,对应 CUDA main.h 的宏
const WEAK    : u32 = 0u;
const STRONG  : u32 = 1u;
const UNKNOWN : u32 = 2u;

// ─── ConfidenceCompute ────────────────────────────────────────
// 前向投影到每个被选中的源视图,统计一致性:
//   存在深度 +1、重投影像素误差 ≤2px +2、相对深度差 ≤2% +2,基数 1,封顶 255
fn confidence_compute(p : vec2<i32>) -> u32 {
  let ref_cam = cams[0];
  let center = u32(p.x + p.y * i32(P.width));
  let selected_view = selected_views[center];

  // ⚠️ 原版这里取的是 plane_hypotheses[center].w 当 ref_depth。
  //    注意 .w 在传播阶段是平面到原点的距离 d,不是深度 ——
  //    上游在进入这一段前会把 .w 改写成深度(见 GetDepthandNormal)。
  //    照抄语义:此处 .w 就是深度。
  let ref_depth = plane_hypotheses[center].w;
  if (ref_depth <= 0.0) {
    return 0xFFFFFFFFu;   // 哨兵:调用方据此把 weak_info 置为 UNKNOWN
  }

  let fwd = get_3d_point_on_world(f32(p.x), f32(p.y), ref_depth, ref_cam);
  var num_consistence = 1;              // 照抄:基数就是 1
  let exist_in_src_weight  = 1;
  let reproj_pixel_weight  = 2;
  let reproj_depth_weight  = 2;

  for (var i : u32 = 0u; i < P.num_images - 1u; i = i + 1u) {
    if (!is_set(selected_view, i)) { continue; }

    let src_idx = i32(i) + 1;
    let src_cam = cams[src_idx];
    let sp = project_on_camera(fwd, src_cam);

    // 最近邻取深度(与 ComputeGeomConsistencyCost 同口径:先取整再加半像素)
    let su = (floor(sp.x) + 0.5) / f32(src_cam.width);
    let sv = (floor(sp.y) + 0.5) / f32(src_cam.height);
    let src_depth = textureSampleLevel(depth_tex, samp_nearest,
                                       vec2<f32>(su, sv), src_idx, 0.0).r;
    if (src_depth <= 0.0) { continue; }

    num_consistence = num_consistence + exist_in_src_weight;

    let src3d = get_3d_point_on_world(sp.x, sp.y, src_depth, src_cam);
    let bp = project_on_camera(src3d, ref_cam);
    let dcol = f32(p.x) - bp.x;
    let drow = f32(p.y) - bp.y;
    if (sqrt(dcol * dcol + drow * drow) <= 2.0) {
      num_consistence = num_consistence + reproj_pixel_weight;
    }
    // bp.z 即 ProjectonCamera_cu 输出的 ref_d
    if (abs(ref_depth - bp.z) / ref_depth <= 0.02) {
      num_consistence = num_consistence + reproj_depth_weight;
    }
  }
  return u32(min(num_consistence, 255));
}

// ─── FindNearestStrongPoint ───────────────────────────────────
// 对每个 WEAK/UNKNOWN 像素,在 ±100 的方窗里找最近的 STRONG 点
// (且其 confidence 不低于本像素的 confidence);平手时取 confidence 更高的。
// STRONG 像素则指向自己。
//
// 🔴 见文件头的性能炸弹说明:201×201 暴力搜索,照抄不改。
fn find_nearest_strong_point(p : vec2<i32>) -> vec2<i32> {
  let width  = i32(P.width);
  let height = i32(P.height);
  let center = u32(p.x + p.y * width);
  let info = unpack_weak_info(packed_maps[center]);

  if (info == STRONG) { return p; }
  if (info != WEAK && info != UNKNOWN) { return vec2<i32>(-1, -1); }

  let center_confidence = unpack_confidence(packed_maps[center]);
  var best_confidence = 0u;
  var best_point = vec2<i32>(-1, -1);
  var min_dist = 3.4028235e38;          // FLT_MAX
  let radius = 100;

  for (var x = -radius; x <= radius; x = x + 1) {
    for (var y = -radius; y <= radius; y = y + 1) {
      let tp = vec2<i32>(p.x + x, p.y + y);
      if (tp.x < 0 || tp.x >= width || tp.y < 0 || tp.y >= height) { continue; }
      let tc = u32(tp.x + tp.y * width);
      if (unpack_weak_info(packed_maps[tc]) != STRONG) { continue; }
      let tconf = unpack_confidence(packed_maps[tc]);
      if (tconf < center_confidence) { continue; }

      let td = sqrt(f32(x * x + y * y));
      if (td < min_dist) {
        min_dist = td;
        best_point = tp;
        best_confidence = tconf;
      } else if (td == min_dist) {
        // ⚠️ 浮点相等比较,照抄原版(td 是 sqrt 的结果,相等只在同距离时成立)
        if (tconf > best_confidence) {
          best_point = tp;
          best_confidence = tconf;
        }
      }
    }
  }
  return best_point;
}
