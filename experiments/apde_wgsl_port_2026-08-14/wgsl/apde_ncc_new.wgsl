// APDe-MVS → WGSL:ComputeBilateralNCCNew(可变形 NCC)+ GetAnchorPoint + Softmax
// 源:whoiszzj/APDe-MVS(MIT) APD.cu:425 / :431 / :448
//
// 这是 APD 相对 ACMMP 的真正加分项:弱纹理像素不再用自己周围的方窗算 NCC
// (那里没纹理,NCC 无意义),而是**借用 GenAnchors 找到的 8 个强纹理锚点**
// 各自算一个 NCC,再用 softmax 加权融合,和自己那一份按 0.25 / 0.75 混合。
//
// 🔴 勘误(2026-08-14 搬运时逐行核对源码后推翻交接说明的一条结论):
//    交接说明第 3.2 节写「SpatialGauss/RangeGauss 的存在说明 NCCNew 里
//    双边权重是真启用的」—— **错的**。实测两条证据:
//      ① APD.cu:534 `float weight = 1.0f;` —— NCCNew 内循环的权重同样是
//         硬编码 1.0,和 NCCOld 一模一样,内循环里没有任何 exp()。
//      ② `grep -n "SpatialGauss\|RangeGauss" APD.cu` 只有两行(定义本身),
//         **零调用点** —— 这两个函数是上游的死代码。
//    ⇒ "Bilateral" 这个名字在整份 APD.cu 里都是空头衔。照抄,不代它修好。
//
// ⚠️ 代价规模:k=0 用 strong_radius/increment(5/2 ⇒ 6×6=36 次取样),
//    k=1..8 用 weak_radius/increment(5/5 ⇒ 3×3=9 次取样)。
//    单次 NCCNew ≈ 36 + 8×9 = 108 次取样,是 NCCOld(36 次)的 3 倍。

// ─── GetAnchorPoint(APD.cu:425)────────────────────────────────
// 原版 short2 anchors_cuda[anchors_map[center]*ANCHOR_NUM + index]。
// 我们把 short2 打进 u32(高 16 位 y,低 16 位 x),(-1,-1) 存 0xFFFFFFFF。
fn get_anchor_point(p : vec2<i32>, index : u32) -> vec2<i32> {
  let offset = u32(anchors_map[p.x + p.y * i32(P.width)]) * ANCHOR_NUM;
  let packed = anchors_out[offset + index];
  // 逐分量还原 -1,与原版 `anchor_pt.x == -1 || anchor_pt.y == -1` 同语义
  let ax = packed & 0xFFFFu;
  let ay = packed >> 16u;
  if (ax == 0xFFFFu || ay == 0xFFFFu) { return vec2<i32>(-1, -1); }
  return vec2<i32>(i32(ax), i32(ay));
}

// ─── Softmax(APD.cu:431)───────────────────────────────────────
// 原版原地改写 float* costs,长度是 strong_costs_num ≤ ANCHOR_NUM-1 = 8。
// C6:WGSL 不能传可变数组指针 ⇒ 值进值出,长度固定 9(调用点上限)。
fn softmax9(costs_in : array<f32, 9>, n : i32) -> array<f32, 9> {
  var c = costs_in;
  var max_cost = -1e10;
  for (var i = 0; i < n; i = i + 1) {
    if (c[i] > max_cost) { max_cost = c[i]; }
  }
  var sum = 0.0;
  for (var i = 0; i < n; i = i + 1) {
    c[i] = exp(c[i] - max_cost);
    sum = sum + c[i];
  }
  for (var i = 0; i < n; i = i + 1) {
    c[i] = c[i] / sum;
  }
  return c;
}

// ─── ComputeBilateralNCCNew(APD.cu:448)────────────────────────
fn compute_bilateral_ncc_new(p : vec2<i32>, src_idx : i32,
                             plane : vec4<f32>) -> f32 {
  let ref_cam = cams[0];
  let src_cam = cams[src_idx];
  let width  = i32(P.width);
  let height = i32(P.height);
  let center = p.x + p.y * width;

  let rw = f32(ref_cam.width);  let rh = f32(ref_cam.height);
  let sw = f32(src_cam.width);  let sh = f32(src_cam.height);

  let center_sa_id = unpack_sa_mask(packed_maps[center]);
  let use_sa_mask  = center_sa_id != 0u;

  let H = compute_homography(ref_cam, src_cam, plane);
  let pt = compute_corresponding_point(H, p);
  if (pt.x >= sw || pt.x < 0.0 || pt.y >= sh || pt.y < 0.0) { return COST_MAX; }

  var cost = 0.0;
  var strong_costs : array<f32, 9>;
  for (var i = 0; i < 9; i = i + 1) { strong_costs[i] = 0.0; }
  var strong_costs_num = 0;

  // ⚠️ 原版这里是 `if (weak_info[center] == WEAK) { ... } else { printf("error\n"); }`
  //    —— 非 WEAK 走到这里是上游的编程错误,返回未初始化前的 cost = 0.0f。
  //    照抄这个语义(返回 0.0),不"顺手"改成 COST_MAX:改了会在 parity
  //    对拍时掩盖掉"调用点用错函数"这一类真 bug。
  if (unpack_weak_info(packed_maps[center]) != WEAK) { return 0.0; }

  var center_cost  = 0.0;
  var strong_cost  = 0.0;
  var strong_weight = 0.0;

  for (var k : u32 = 0u; k < ANCHOR_NUM; k = k + 1u) {
    let anchor_pt = get_anchor_point(p, k);
    if (anchor_pt.x == -1 || anchor_pt.y == -1) { continue; }
    if (use_sa_mask) {
      if (unpack_sa_mask(packed_maps[anchor_pt.x + anchor_pt.y * width]) != center_sa_id) {
        continue;
      }
    }

    let anchor_src_pt = compute_corresponding_point(H, anchor_pt);
    // ⚠️ 原版这里的边界用的是 **ref 图的 width/height**(helper->width/height),
    //    不是 src_camera.width/height —— 与函数上方那次早退检查口径不一致。
    //    看起来是上游笔误,但照抄:两图同分辨率时无差,不同分辨率时行为不同,
    //    parity 对拍要认这一条。
    if (anchor_src_pt.x < 0.0 || anchor_src_pt.y < 0.0
        || anchor_src_pt.x >= f32(width) || anchor_src_pt.y >= f32(height)) {
      if (k != 0u) {
        let view_info = selected_views[anchor_pt.x + anchor_pt.y * width];
        if (is_set(view_info, u32(src_idx - 1))) {
          strong_costs[strong_costs_num] = COST_MAX;
          strong_costs_num = strong_costs_num + 1;
          strong_weight = strong_weight + 1.0;
        }
        continue;
      } else {
        return COST_MAX;
      }
    }

    // ── 该锚点自己的一份 NCC ──────────────────────────────────
    var sum_ref = 0.0; var sum_ref_ref = 0.0;
    var sum_src = 0.0; var sum_src_src = 0.0;
    var sum_ref_src = 0.0; var wsum = 0.0;

    // ⚠️ 原版在这里第二次声明了 ref_center_pix(APD.cu:483 与 :520),
    //    两次都**从未被使用** —— 是上游遗留的死变量,不搬。
    let radius = select(P.weak_radius,    P.strong_radius,    k == 0u);
    let inc    = select(P.weak_increment, P.strong_increment, k == 0u);

    var i = -radius;
    loop {
      if (i > radius) { break; }
      var j = -radius;
      loop {
        if (j > radius) { break; }
        let ref_pt = vec2<i32>(anchor_pt.x + i, anchor_pt.y + j);
        // ⚠️ 原版对 ref_pt **没有任何边界检查**就去索引 sa_mask[ref_pt...]
        //    (APD.cu:527)—— 在 CUDA 上是越界读相邻显存。
        //    WGSL/Metal 的 storage 索引会被 naga 钳制到界内,所以我们不会
        //    读到"相邻行的真实像素",而是读到钳制后的值。
        //    ⇒ **图像四边一圈上的行为与 CUDA 版不同**,已登记进偏离账。
        //       这属于"移植使之更安全",不是抄错。
        if (use_sa_mask) {
          if (unpack_sa_mask(packed_maps[ref_pt.x + ref_pt.y * width]) != center_sa_id) {
            j = j + inc;
            continue;
          }
        }
        let ref_pix = sample_gray(ref_tex, samp, f32(ref_pt.x), f32(ref_pt.y), rw, rh);
        let src_pt  = compute_corresponding_point(H, ref_pt);
        let src_pix = sample_gray_src(samp, src_idx, src_pt.x, src_pt.y, sw, sh);
        // weight 恒为 1.0(照抄原版 APD.cu:534 —— 见文件头勘误)
        sum_ref     = sum_ref     + ref_pix;
        sum_ref_ref = sum_ref_ref + ref_pix * ref_pix;
        sum_src     = sum_src     + src_pix;
        sum_src_src = sum_src_src + src_pix * src_pix;
        sum_ref_src = sum_ref_src + ref_pix * src_pix;
        wsum        = wsum + 1.0;
        j = j + inc;
      }
      i = i + inc;
    }

    if (wsum == 0.0) { continue; }

    // ⚠️ 这里**不**复用 ncc_finalize:原版 NCCNew 的收尾控制流与 NCCOld 不同
    //    (方差过小时是 temp_cost = cost_max **继续走下去**,不是 return),
    //    逐行内联才对得上。
    let inv = 1.0 / wsum;
    let mr  = sum_ref * inv;
    let mrr = sum_ref_ref * inv;
    let ms  = sum_src * inv;
    let mss = sum_src_src * inv;
    let mrs = sum_ref_src * inv;
    let var_ref = mrr - mr * mr;
    let var_src = mss - ms * ms;
    var temp_cost = 0.0;
    if (var_ref < K_MIN_VAR || var_src < K_MIN_VAR) {
      temp_cost = COST_MAX;
    } else {
      let covar = mrs - mr * ms;
      let denom = sqrt(var_ref * var_src);
      temp_cost = max(0.0, min(COST_MAX, 1.0 - covar / denom));
    }

    if (k == 0u) {
      center_cost = temp_cost;
    } else {
      strong_costs[strong_costs_num] = temp_cost;
      strong_costs_num = strong_costs_num + 1;
      strong_weight = strong_weight + 1.0;
    }
  }

  if (strong_weight <= 1e-6) {
    cost = center_cost;
  } else {
    // softmax 的输入是 strong_costs 的副本,加权时用的是**原始** strong_costs
    let w = softmax9(strong_costs, strong_costs_num);
    strong_cost = 0.0;
    for (var i = 0; i < strong_costs_num; i = i + 1) {
      strong_cost = strong_cost + w[i] * strong_costs[i];
    }
    strong_cost = min(strong_cost, COST_MAX);
    cost = 0.25 * center_cost + 0.75 * strong_cost;
  }
  return cost;
}
