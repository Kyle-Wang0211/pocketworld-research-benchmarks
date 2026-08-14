// APDe-MVS → WGSL 移植:公共类型与叶子数学函数
// 源:whoiszzj/APDe-MVS(MIT) APD.cu / APD.h
//
// ⚠️ 本文件是 spike,只为量速度,未做产品化。GPL 血统取证(上游 README 称
//    "largely benefits from Gipuma",Gipuma 是 GPL-3.0)尚未完成,在取证通过前
//    任何代码都不得进入产品树。
//
// ─── 五条跨端约束(2026-08-14 调研定,详见备忘)───────────────────────
// C1  iOS 每 stage 只有约 10 个 storage buffer(Metal 30 槽扣 base 算出)。
//     原版 14 个超限 ⇒ 4 张 uchar 图打包进 packed_maps 的 4 个字节通道。
// C2  Metal 没有 runtime array length(无 OpArrayLength 等价物)⇒ 所有长度
//     走 uniform,shader 内一律不查数组长度。
// C3  workgroup size 在 Metal 是 host 侧参数(threadsPerThreadgroup),在
//     WGSL 是 shader 内字面量 ⇒ 必须单一数据源。本文件的 WG_X/WG_Y 是那个
//     唯一来源,host 侧常量由构建期从这里生成,不得手写。
// C4  纹理用 f16 而非 f32:rgba16float 默认可过滤(硬件双线性免费),
//     r32float 默认是 unfilterable-float 需额外 feature。顺带省一半带宽。
// C5  binding 布局在转译期冻结。Vulkan↔Metal 的 binding 语义不是 1:1
//     (资源数组在 MSL 占多个 id;combined image sampler 要拆两个)⇒ 这里
//     刻意只用「分离的 texture + sampler」,不用 combined,避免 remap。
// ────────────────────────────────────────────────────────────────

// C3:workgroup 尺寸的唯一来源。改这里,host 侧跟着重新生成。
const WG_X : u32 = 16u;
const WG_Y : u32 = 16u;

const MAX_IMAGES : u32 = 32u;   // 对齐 main.h:40
const ANCHOR_NUM : u32 = 9u;    // 对齐 main.h:41

// 相机:CUDA 版是 float K[9]/R[9]/t[3] 的裸数组。
//
// ⚠️ 修正记录(spike 期):初版只存了 fx/fy/cx/cy 四个内参,是错的 ——
//    ComputeHomography 用到完整 R[9],ProjectonCamera_cu 用到完整 K[9]
//    (含 K[1] 斜切与 K[6..8] 底行)。虽然我们的相机是标准针孔
//    (K[1]=K[3]=K[6]=K[7]=0, K[8]=1),但为了与 CUDA 版逐位对拍,
//    这里忠实存全量。相机是逐图的(≤32 个),不是逐像素,开销可忽略。
//
// WGSL 里用 mat3x3 会引入 16 字节列对齐,和 host 侧 std430 打包容易错位,
// 这里保持扁平 f32 语义,按 vec4 边界填充,host 侧按同样布局写。
struct Camera {
  // K 行主序:K0..K8 = [K0 K1 K2; K3 K4 K5; K6 K7 K8]
  K0 : vec4<f32>,   // K[0..2] + pad
  K1 : vec4<f32>,   // K[3..5] + pad
  K2 : vec4<f32>,   // K[6..8] + pad
  // R 行主序
  R0 : vec4<f32>,   // R[0..2] + pad
  R1 : vec4<f32>,   // R[3..5] + pad
  R2 : vec4<f32>,   // R[6..8] + pad
  t  : vec4<f32>,   // 平移 + pad
  // ⚠️ 补记(第三次漏字段):Get3DPointonWorld_cu 用 camera.c[3](相机中心)。
  //    CUDA 版把 c 和 t 都存着,c = -R^T·t 是预算好的。照存。
  c  : vec4<f32>,   // 相机中心 + pad
  depth_min : f32, depth_max : f32,
  // ⚠️ 补记(spike 期第二次漏字段):CUDA 的 Camera 带 width/height,
  //    ComputeBilateralNCCOld 用 src_camera.width/height 做投影点边界检查,
  //    也用 ref_camera.width 算 sa_mask 索引。少了它对不上。
  width : i32, height : i32,
};

// 便捷取值:与 CUDA 的 camera.K[i] / camera.R[i] 逐位对应
fn cam_fx(c : Camera) -> f32 { return c.K0.x; }   // K[0]
fn cam_cx(c : Camera) -> f32 { return c.K0.z; }   // K[2]
fn cam_fy(c : Camera) -> f32 { return c.K1.y; }   // K[4]
fn cam_cy(c : Camera) -> f32 { return c.K1.z; }   // K[5]

// C2:所有尺寸/数量走这里,shader 内不查数组长度
struct Params {
  width       : u32,
  height      : u32,
  ref_index   : u32,
  num_images  : u32,   // 实际视图数(≤ MAX_IMAGES)
  num_anchors : u32,   // anchors 数组的真实长度
  iter        : u32,
  // NCC 窗口:对应 CUDA 的 params->strong_radius / strong_increment
  strong_radius    : i32,
  strong_increment : i32,
  // 🔴 确定性种子:CUDA 原版是 curand_init(clock64(), ...),用 GPU 时钟播种,
  //    跑两次结果不同,直接撞"交付绝对无损/可复现"铁律。
  //    这里改成由 host 传入的固定种子 + 像素索引哈希 ⇒ 默认逐字节可复现。
  //    这是移植期主动做的一处偏离,已记录,不是照抄失误。
  rand_seed : u32,
  // 精修与代价聚合用(对应 CUDA PatchMatchParams 同名字段)
  depth_min        : f32,
  depth_max        : f32,
  geom_factor      : f32,
  geom_consistency : u32,   // 0/1,WGSL 无 bool in uniform
  use_impetus      : u32,   // 0/1
  state            : u32,   // 对应 CUDA params->state;REFINE_INIT 见常量
  // GenAnchors 用(对应 CUDA PatchMatchParams 同名字段)
  rotate_time      : u32,   // 原版取值 [1,2,4]
  ransac_threshold : f32,
  _pad_p0          : u32,
  _pad_p1          : u32,
};

// 对应 CUDA 的 state 枚举(main.h)。只用到 REFINE_INIT 这一档的分支。
const STATE_REFINE_INIT : u32 = 1u;


// ─── 叶子数学:与 CUDA 版逐行对应 ───────────────────────────────

// CUDA: Vec3DotVec3(float4,float4) — 只取 xyz
fn vec3_dot(a : vec4<f32>, b : vec4<f32>) -> f32 {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

// CUDA: NormalizeVec3 — 原版用 rsqrtf,WGSL 的 inverseSqrt 语义相同
fn normalize_vec3(v : vec4<f32>) -> vec4<f32> {
  let n2 = v.x * v.x + v.y * v.y + v.z * v.z;
  let inv = inverseSqrt(n2);
  return vec4<f32>(v.x * inv, v.y * inv, v.z * inv, v.w);
}

// CUDA: Mat33DotVec3(mat[9], vec, result)
fn mat33_dot_vec3(r0 : vec4<f32>, r1 : vec4<f32>, r2 : vec4<f32>, v : vec4<f32>) -> vec4<f32> {
  return vec4<f32>(
    r0.x * v.x + r0.y * v.y + r0.z * v.z,
    r1.x * v.x + r1.y * v.y + r1.z * v.z,
    r2.x * v.x + r2.y * v.y + r2.z * v.z,
    0.0);
}

// CUDA: Get3DPoint(camera, p, depth, X)
fn get_3d_point(cam : Camera, p : vec2<i32>, depth : f32) -> vec3<f32> {
  return vec3<f32>(
    depth * (f32(p.x) - cam_cx(cam)) / cam_fx(cam),
    depth * (f32(p.y) - cam_cy(cam)) / cam_fy(cam),
    depth);
}

// CUDA: GetDistance2Origin
fn get_distance_to_origin(cam : Camera, p : vec2<i32>, depth : f32, normal : vec4<f32>) -> f32 {
  let X = get_3d_point(cam, p, depth);
  return -(normal.x * X.x + normal.y * X.y + normal.z * X.z);
}

// CUDA: ComputeDepthfromPlaneHypothesis
// 原式用 K[0]=fx, K[2]=cx, K[4]=fy, K[5]=cy
fn depth_from_plane(cam : Camera, plane : vec4<f32>, p : vec2<i32>) -> f32 {
  let denom = (f32(p.x) - cam_cx(cam)) * plane.x
            + (cam_fx(cam) / cam_fy(cam)) * (f32(p.y) - cam_cy(cam)) * plane.y
            + cam_fx(cam) * plane.z;
  return -plane.w * cam_fx(cam) / denom;
}

// ─── C1:打包的 uchar 图 ─────────────────────────────────────────
// 原版四张独立 uchar buffer:weak_info / confidence / sa_mask / weak_reliable
// 打进一个 u32 的四个字节。索引 = y*width + x。
fn unpack_weak_info(v : u32)     -> u32 { return  v        & 0xFFu; }
fn unpack_confidence(v : u32)    -> u32 { return (v >>  8u) & 0xFFu; }
fn unpack_sa_mask(v : u32)       -> u32 { return (v >> 16u) & 0xFFu; }
fn unpack_weak_reliable(v : u32) -> u32 { return (v >> 24u) & 0xFFu; }

// CUDA 版的 setBit/isSet 作用在 selected_views 的位图上,语义不变
fn is_set(bits : u32, n : u32) -> bool { return ((bits >> n) & 1u) == 1u; }
fn set_bit(bits : u32, n : u32) -> u32 { return bits | (1u << n); }
