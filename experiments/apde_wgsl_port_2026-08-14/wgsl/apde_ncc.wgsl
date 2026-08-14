// APDe-MVS → WGSL:ComputeBilateralNCCOld(热点内循环)
// 源:whoiszzj/APDe-MVS(MIT) APD.cu
// 依赖 apde_common.wgsl + apde_geom.wgsl(构建期拼接)
//
// ⚠️ 名字里有 "Bilateral",但两条分支的 weight 都硬编码 1.0f ——
//    双边权重在这份代码里从未启用。内循环没有 exp(),只有纹理取样 + 乘加。
//    照抄,不代它"修好"。
//
// ⚠️ 坐标系转换:CUDA 的 tex2D<float>(img, x+0.5, y+0.5) 用的是
//    非归一化坐标 + 半像素偏移(取像素中心)。WGSL 的 textureSampleLevel
//    要归一化坐标 ⇒ (x+0.5)/W, (y+0.5)/H。这是移植最容易错半个像素的地方,
//    parity 对拍时第一个要查的就是它。

const COST_MAX : f32 = 2.0;
const K_MIN_VAR : f32 = 1e-5;

// 第二分支的自适应 patch:4 象限 × 9 偏移。对应 CUDA 的 sign[8] / offset[18]。
const APD_SIGN : array<vec2<i32>, 4> = array<vec2<i32>, 4>(
  vec2<i32>( 1,  1), vec2<i32>(-1, -1), vec2<i32>( 1, -1), vec2<i32>(-1,  1));
const APD_OFFSET : array<vec2<i32>, 9> = array<vec2<i32>, 9>(
  vec2<i32>(1,1), vec2<i32>(3,1), vec2<i32>(1,3),
  vec2<i32>(1,5), vec2<i32>(3,3), vec2<i32>(5,1),
  vec2<i32>(5,3), vec2<i32>(3,5), vec2<i32>(5,5));

// 纹理取样:等价于 CUDA 的 tex2D<float>(img, x+0.5f, y+0.5f)
// C4:纹理用可过滤格式,硬件双线性免费。
fn sample_gray(t : texture_2d<f32>, s : sampler, x : f32, y : f32, w : f32, h : f32) -> f32 {
  return textureSampleLevel(t, s, vec2<f32>((x + 0.5) / w, (y + 0.5) / h), 0.0).r;
}

// 源图版:按 src_idx 取纹理数组的对应层(对应原版 images[src_idx])
fn sample_gray_src(s : sampler, layer : i32, x : f32, y : f32, w : f32, h : f32) -> f32 {
  return textureSampleLevel(src_tex, s, vec2<f32>((x + 0.5) / w, (y + 0.5) / h), layer, 0.0).r;
}

// ⚠️ 移植期自查:我最初把这段抽成共享函数,但原版是两条分支各自
//    复制粘贴的。抽取虽然行为等价,却违反"逐行照抄"原则 ——
//    将来 parity 对不上时无法排除是这里引入的。
//    现改回:两条分支各自内联调用它,调用点与原版一一对应,
//    函数体本身保持与原版逐行相同。
fn ncc_finalize(sum_ref : f32, sum_ref_ref : f32, sum_src : f32,
                sum_src_src : f32, sum_ref_src : f32, wsum : f32) -> f32 {
  if (wsum <= 0.0) { return COST_MAX; }
  let inv = 1.0 / wsum;
  let mr  = sum_ref * inv;
  let mrr = sum_ref_ref * inv;
  let ms  = sum_src * inv;
  let mss = sum_src_src * inv;
  let mrs = sum_ref_src * inv;

  let var_ref = mrr - mr * mr;
  let var_src = mss - ms * ms;
  if (var_ref < K_MIN_VAR || var_src < K_MIN_VAR) { return COST_MAX; }

  let covar = mrs - mr * ms;
  let denom = sqrt(var_ref * var_src);
  return max(0.0, min(COST_MAX, 1.0 - covar / denom));
}

fn compute_bilateral_ncc(
  p : vec2<i32>,
  ref_cam : Camera, src_cam : Camera, src_idx : i32,
  plane : vec4<f32>
) -> f32 {
  // ⚠️ ref_tex/src_tex/samp/packed_maps/P 全部直接引用模块级 binding ——
  //    WGSL 不允许传 storage 指针,详见 apde_bindings.wgsl 的说明。
  let rw = f32(ref_cam.width);  let rh = f32(ref_cam.height);
  let sw = f32(src_cam.width);  let sh = f32(src_cam.height);

  let center_sa_id = unpack_sa_mask(packed_maps[p.x + p.y * ref_cam.width]);

  let H = compute_homography(ref_cam, src_cam, plane);
  let pt = compute_corresponding_point(H, p);
  // 边界:投影点落在 src 图外 ⇒ 直接给最大代价
  if (pt.x >= sw || pt.x < 0.0 || pt.y >= sh || pt.y < 0.0) { return COST_MAX; }

  // ⚠️ 原版 const int center = pt.y * src_camera.width + pt.x 是 float→int
  //    的隐式截断(向零取整)。WGSL 必须显式 i32(),语义相同。
  let center = i32(pt.y) * src_cam.width + i32(pt.x);
  let center_mask = unpack_sa_mask(packed_maps[center]);

  var sum_ref = 0.0; var sum_ref_ref = 0.0;
  var sum_src = 0.0; var sum_src_src = 0.0;
  var sum_ref_src = 0.0; var wsum = 0.0;

  if (center_mask == 0u) {
    // ── 分支 A:规则方窗(strong 区)────────────────────────────
    let radius = P.strong_radius;
    let inc    = P.strong_increment;
    var i = -radius;
    loop {
      if (i > radius) { break; }
      var j = -radius;
      loop {
        if (j > radius) { break; }
        let rpt = vec2<i32>(p.x + i, p.y + j);
        let ref_pix = sample_gray(ref_tex, samp, f32(rpt.x), f32(rpt.y), rw, rh);
        let spt = compute_corresponding_point(H, rpt);
        let src_pix = sample_gray_src(samp, src_idx, spt.x, spt.y, sw, sh);
        // weight 恒为 1.0(照抄原版)
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
  } else {
    // ── 分支 B:自适应形变 patch(APD 的核心)─────────────────
    // 4 象限,每象限沿 9 个偏移走,碰到 sa_mask 不同即 break(只跳内层)
    for (var q = 0; q < 4; q = q + 1) {
      let sgn = APD_SIGN[q];
      for (var k = 0; k < 9; k = k + 1) {
        let off = APD_OFFSET[k];
        let rpt = vec2<i32>(p.x + off.x * sgn.x, p.y + off.y * sgn.y);
        if (rpt.x < 0 || rpt.x >= ref_cam.width || rpt.y < 0 || rpt.y >= ref_cam.height) {
          continue;
        }
        let ridx = rpt.y * ref_cam.width + rpt.x;
        if (unpack_sa_mask(packed_maps[ridx]) != center_sa_id) { break; }
        let ref_pix = sample_gray(ref_tex, samp, f32(rpt.x), f32(rpt.y), rw, rh);
        let spt = compute_corresponding_point(H, rpt);
        let src_pix = sample_gray_src(samp, src_idx, spt.x, spt.y, sw, sh);
        sum_ref     = sum_ref     + ref_pix;
        sum_ref_ref = sum_ref_ref + ref_pix * ref_pix;
        sum_src     = sum_src     + src_pix;
        sum_src_src = sum_src_src + src_pix * src_pix;
        sum_ref_src = sum_ref_src + ref_pix * src_pix;
        wsum        = wsum + 1.0;
      }
    }
  }

  return ncc_finalize(sum_ref, sum_ref_ref, sum_src, sum_src_src, sum_ref_src, wsum);
}
