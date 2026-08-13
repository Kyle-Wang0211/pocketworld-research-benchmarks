// APDe-MVS → WGSL:随机数 + 法向生成
// 源:whoiszzj/APDe-MVS(MIT) APD.cu
//
// ─── 与官方的关系(先说清楚,别当成完全等价)──────────────────
// ✅ 生成器逐行照抄 cuRAND 的 XORWOW(见 xorwow_next / rand_uniform)
// 🔴 播种没有照抄:curand_init(clock64(), p.y, p.x, ...) 有两处不能照搬
//    ① clock64() 是 GPU 时钟 ⇒ 跑两次结果不同,撞"交付绝对无损/可复现"铁律
//    ② curand_init 的 2^67 skipahead 要矩阵幂表,WGSL 里代价过高
//    ⇒ 改成 (rand_seed, 像素索引) 哈希播种。
//
//    后果说明白:给定种子的数列**不会**与 CUDA 逐位相同,所以做数值
//    parity 对拍时,随机路径上的差异是预期内的,不能当 bug 查。
//    PatchMatch 只依赖"有个随机初始化",不依赖具体数列 —— 这一点与
//    扩散模型的噪声有本质区别(那个改了会动模型行为)。
//    host 想复现原版的不可复现行为,把 rand_seed 设成时间戳即可;默认固定。
//
// 状态存 6 个 u32(24 B/px),比原版 curandState 的 48 B/px 省一半 ——
// 省的是 boxmuller 缓存等我们不用的字段,不是算法删减。

// ─── curand XORWOW —— 照抄官方生成器 ────────────────────────
// 源:CUDA cuRAND 的 curandStateXORWOW / Marsaglia XORWOW。
// 状态 = v[5] + d,共 6 个 u32(原版 curandState 是 48 字节,
// 这里 24 字节 —— 差的是 boxmuller 缓存等我们用不到的字段)。
//
// ⚠️ 逐位复刻的边界(说清楚,别当成完全等价):
//    · 生成器本身(下面这个 xorwow_next)是**逐行照抄**官方算法
//    · 但 curand_init(seed, subsequence, offset) 的 2^67 skipahead
//      需要矩阵幂表,那部分**没有**复刻,改用哈希播种。
//    ⇒ 给定种子的**数列不会与 CUDA 逐位相同**,但生成器的统计性质相同。
//    PatchMatch 只依赖"有个随机初始化",不依赖具体数列。

struct RandState { v0:u32, v1:u32, v2:u32, v3:u32, v4:u32, d:u32 };

// 照抄 curand() for XORWOW
fn xorwow_next(s : ptr<function, RandState>) -> u32 {
  let t = (*s).v0 ^ ((*s).v0 >> 2u);
  (*s).v0 = (*s).v1;
  (*s).v1 = (*s).v2;
  (*s).v2 = (*s).v3;
  (*s).v3 = (*s).v4;
  (*s).v4 = ((*s).v4 ^ ((*s).v4 << 4u)) ^ (t ^ (t << 1u));
  (*s).d  = (*s).d + 362437u;
  return (*s).v4 + (*s).d;
}

// 照抄 curand_uniform:_curand_uniform(x) = x*2^-32 + 2^-33,返回 (0,1]
const CURAND_2POW32_INV : f32 = 2.3283064e-10;
fn rand_uniform(s : ptr<function, RandState>) -> f32 {
  return f32(xorwow_next(s)) * CURAND_2POW32_INV + (CURAND_2POW32_INV * 0.5);
}

// 播种。⚠️ 这一处**不是**复刻 curand_init —— 见上面的边界说明。
//    确定性:同一个 (seed, idx) 永远给出同一个流(铁律要求)。
fn seed_state(seed : u32, idx : u32) -> RandState {
  var h = idx * 747796405u + seed * 2891336453u;
  var st : RandState;
  h = (h ^ (h >> 16u)) * 0x45d9f3b5u; st.v0 = h | 1u;
  h = (h ^ (h >> 16u)) * 0x45d9f3b5u; st.v1 = h | 1u;
  h = (h ^ (h >> 16u)) * 0x45d9f3b5u; st.v2 = h | 1u;
  h = (h ^ (h >> 16u)) * 0x45d9f3b5u; st.v3 = h | 1u;
  h = (h ^ (h >> 16u)) * 0x45d9f3b5u; st.v4 = h | 1u;
  st.d = 6615241u;   // curand_init 的 d 初值
  // 预热若干次,消掉低质量的初始状态
  for (var i = 0; i < 16; i = i + 1) { let _u = xorwow_next(&st); }
  return st;
}

// ─── GetViewDirection ─────────────────────────────────────────
fn get_view_direction(cam : Camera, p : vec2<i32>, depth : f32) -> vec4<f32> {
  let X = get_3d_point(cam, p, depth);
  let n = sqrt(X.x * X.x + X.y * X.y + X.z * X.z);
  return vec4<f32>(X.x / n, X.y / n, X.z / n, 0.0);
}

// ─── Get3DPointonWorld_cu ─────────────────────────────────────
// ⚠️ 注意这里的旋转用的是 R 的**列**(R[0],R[3],R[6] 作一行),
//    即 R^T —— 相机系→世界系。别写成 R。
fn get_3d_point_on_world(x : f32, y : f32, depth : f32, cam : Camera) -> vec3<f32> {
  let px = depth * (x - cam_cx(cam)) / cam_fx(cam);
  let py = depth * (y - cam_cy(cam)) / cam_fy(cam);
  let pz = depth;
  let tx = cam.R0.x * px + cam.R1.x * py + cam.R2.x * pz;
  let ty = cam.R0.y * px + cam.R1.y * py + cam.R2.y * pz;
  let tz = cam.R0.z * px + cam.R1.z * py + cam.R2.z * pz;
  return vec3<f32>(tx + cam.c.x, ty + cam.c.y, tz + cam.c.z);
}

// ─── GenerateRandomNormal ─────────────────────────────────────
// Marsaglia 方法在单位球上均匀取点,再翻到背对视线的半球
fn generate_random_normal(cam : Camera, p : vec2<i32>,
                          state : ptr<function, RandState>, depth : f32) -> vec4<f32> {
  var q1 = 1.0;
  var q2 = 1.0;
  var s  = 2.0;
  // ⚠️ 原版是 while(s >= 1.0) 无上限。GPU 上无界循环有挂死风险,
  //    这里加 64 次上限兜底(期望迭代次数 ≈ 1.27,64 次的失败概率 ~1e-10)。
  //    这是可移植性加固,不改变分布。
  var guard = 0;
  loop {
    q1 = 2.0 * rand_uniform(state) - 1.0;
    q2 = 2.0 * rand_uniform(state) - 1.0;
    s  = q1 * q1 + q2 * q2;
    guard = guard + 1;
    if (s < 1.0 || guard >= 64) { break; }
  }
  if (s >= 1.0) { s = 0.5; q1 = 0.5; q2 = 0.5; }   // 兜底,几乎不会走到

  let sq = sqrt(1.0 - s);
  var normal = vec4<f32>(2.0 * q1 * sq, 2.0 * q2 * sq, 1.0 - 2.0 * s, 0.0);

  let vd = get_view_direction(cam, p, depth);
  if (vec3_dot(normal, vd) > 0.0) {
    normal = vec4<f32>(-normal.x, -normal.y, -normal.z, normal.w);
  }
  return normalize_vec3(normal);
}

// ─── GeneratePerturbedNormal ──────────────────────────────────
fn generate_perturbed_normal(cam : Camera, p : vec2<i32>, normal : vec4<f32>,
                             state : ptr<function, RandState>, perturbation : f32) -> vec4<f32> {
  let vd = get_view_direction(cam, p, 1.0);

  let a1 = (rand_uniform(state) - 0.5) * perturbation;
  let a2 = (rand_uniform(state) - 0.5) * perturbation;
  let a3 = (rand_uniform(state) - 0.5) * perturbation;

  let s1 = sin(a1); let s2 = sin(a2); let s3 = sin(a3);
  let c1 = cos(a1); let c2 = cos(a2); let c3 = cos(a3);

  // 与 CUDA 的 R[0..8] 逐位对应
  let R0 = vec4<f32>(c2 * c3,  c3 * s1 * s2 - c1 * s3,  s1 * s3 + c1 * c3 * s2, 0.0);
  let R1 = vec4<f32>(c2 * s3,  c1 * c3 + s1 * s2 * s3,  c1 * s2 * s3 - c3 * s1, 0.0);
  let R2 = vec4<f32>(-s2,      c2 * s1,                 c1 * c2,                0.0);

  var np = mat33_dot_vec3(R0, R1, R2, normal);
  // 扰动后若朝向视线同侧,退回原法向(照抄原版)
  if (vec3_dot(np, vd) >= 0.0) { np = normal; }
  return normalize_vec3(np);
}
