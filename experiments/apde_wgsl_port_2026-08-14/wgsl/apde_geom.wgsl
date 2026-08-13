// APDe-MVS → WGSL:几何层(单应 / 对应点 / 投影)
// 源:whoiszzj/APDe-MVS(MIT) APD.cu
// 依赖 apde_common.wgsl(构建期拼接,WGSL 无 #include)
//
// 逐行对照 CUDA 版,不做任何"顺手优化" —— spike 的目的是量速度,
// 任何重排都会让 parity 对拍失去意义。

// ─── ComputeHomography ────────────────────────────────────────
// CUDA 版把 H 写进 float H[9]。WGSL 没有输出参数,返回三个行向量。
struct Homography { h0 : vec3<f32>, h1 : vec3<f32>, h2 : vec3<f32> };

fn compute_homography(ref_cam : Camera, src_cam : Camera, plane : vec4<f32>) -> Homography {
  // 相机中心 C = -R^T * t(注意原版用的是 R 的列,即 R 转置乘 t)
  let ref_C = vec3<f32>(
    -(ref_cam.R0.x * ref_cam.t.x + ref_cam.R1.x * ref_cam.t.y + ref_cam.R2.x * ref_cam.t.z),
    -(ref_cam.R0.y * ref_cam.t.x + ref_cam.R1.y * ref_cam.t.y + ref_cam.R2.y * ref_cam.t.z),
    -(ref_cam.R0.z * ref_cam.t.x + ref_cam.R1.z * ref_cam.t.y + ref_cam.R2.z * ref_cam.t.z));
  let src_C = vec3<f32>(
    -(src_cam.R0.x * src_cam.t.x + src_cam.R1.x * src_cam.t.y + src_cam.R2.x * src_cam.t.z),
    -(src_cam.R0.y * src_cam.t.x + src_cam.R1.y * src_cam.t.y + src_cam.R2.y * src_cam.t.z),
    -(src_cam.R0.z * src_cam.t.x + src_cam.R1.z * src_cam.t.y + src_cam.R2.z * src_cam.t.z));

  // R_relative = R_src * R_ref^T
  let sr0 = src_cam.R0.xyz; let sr1 = src_cam.R1.xyz; let sr2 = src_cam.R2.xyz;
  let rr0 = ref_cam.R0.xyz; let rr1 = ref_cam.R1.xyz; let rr2 = ref_cam.R2.xyz;

  let R_rel0 = vec3<f32>(dot(sr0, rr0), dot(sr0, rr1), dot(sr0, rr2));
  let R_rel1 = vec3<f32>(dot(sr1, rr0), dot(sr1, rr1), dot(sr1, rr2));
  let R_rel2 = vec3<f32>(dot(sr2, rr0), dot(sr2, rr1), dot(sr2, rr2));

  let C_rel = ref_C - src_C;
  let t_rel = vec3<f32>(dot(sr0, C_rel), dot(sr1, C_rel), dot(sr2, C_rel));

  // H = R_rel - t_rel * n^T / d
  let n_over_d = plane.xyz / plane.w;
  var h0 = R_rel0 - t_rel.x * n_over_d;
  var h1 = R_rel1 - t_rel.y * n_over_d;
  var h2 = R_rel2 - t_rel.z * n_over_d;

  // 右乘 K_ref^{-1}
  let rfx = cam_fx(ref_cam); let rfy = cam_fy(ref_cam);
  let rcx = cam_cx(ref_cam); let rcy = cam_cy(ref_cam);
  let t0 = vec3<f32>(h0.x / rfx, h0.y / rfy, -h0.x * rcx / rfx - h0.y * rcy / rfy + h0.z);
  let t1 = vec3<f32>(h1.x / rfx, h1.y / rfy, -h1.x * rcx / rfx - h1.y * rcy / rfy + h1.z);
  let t2 = vec3<f32>(h2.x / rfx, h2.y / rfy, -h2.x * rcx / rfx - h2.y * rcy / rfy + h2.z);

  // 左乘 K_src。⚠️ 原版这里用的是 K[0],K[2] / K[4],K[5] / K[8],
  // 即假定 K[1]=K[3]=K[6]=K[7]=0。忠实照抄,不代它化简。
  let sK0 = src_cam.K0.x;  // K[0]
  let sK2 = src_cam.K0.z;  // K[2]
  let sK4 = src_cam.K1.y;  // K[4]
  let sK5 = src_cam.K1.z;  // K[5]
  let sK8 = src_cam.K2.z;  // K[8]

  var out : Homography;
  out.h0 = vec3<f32>(sK0 * t0.x + sK2 * t2.x, sK0 * t0.y + sK2 * t2.y, sK0 * t0.z + sK2 * t2.z);
  out.h1 = vec3<f32>(sK4 * t1.x + sK5 * t2.x, sK4 * t1.y + sK5 * t2.y, sK4 * t1.z + sK5 * t2.z);
  out.h2 = vec3<f32>(sK8 * t2.x, sK8 * t2.y, sK8 * t2.z);
  return out;
}

// ─── ComputeCorrespondingPoint ────────────────────────────────
fn compute_corresponding_point(H : Homography, p : vec2<i32>) -> vec2<f32> {
  let pf = vec3<f32>(f32(p.x), f32(p.y), 1.0);
  let x = dot(H.h0, pf);
  let y = dot(H.h1, pf);
  let z = dot(H.h2, pf);
  return vec2<f32>(x / z, y / z);
}

// ─── ProjectonCamera_cu ───────────────────────────────────────
// 返回 (u, v, depth)。原版是输出参数 point 与 depth。
// ⚠️ 这里必须用完整 K[9]:K[1]/K[3] 是斜切,K[6..8] 是底行。
fn project_on_camera(PointX : vec3<f32>, cam : Camera) -> vec3<f32> {
  let tmp = vec3<f32>(
    dot(cam.R0.xyz, PointX) + cam.t.x,
    dot(cam.R1.xyz, PointX) + cam.t.y,
    dot(cam.R2.xyz, PointX) + cam.t.z);
  let depth = dot(cam.K2.xyz, tmp);            // K[6..8] · tmp
  let u = dot(cam.K0.xyz, tmp) / depth;        // K[0..2] · tmp
  let v = dot(cam.K1.xyz, tmp) / depth;        // K[3..5] · tmp
  return vec3<f32>(u, v, depth);
}
