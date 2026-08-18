// flash_attn v2:修 v1 的并行度灾难。
//
// v1 实测(5090,wgpu/Vulkan):算对了(余弦 0.9999998)但只有 0.01-0.11 TFLOPS,
// 是 PyTorch SDPA 的 1/92。诊断:耗时随 N **线性**增长而不是 N² ⇒ GPU 没在满负荷算。
// 三个病根:
//   ① 一线程包一整行 query ⇒ 总线程数 = N。N=4096 时只有 64 个 workgroup,
//      5090 有 170 个 SM,大部分是空的。
//   ② 每线程私有 `acc[64]` 数组 ⇒ 几乎必然溢出到 local memory,访存爆炸。
//   ③ head 维度靠 4 次串行 dispatch,没铺到并行上。
//
// v2 的对策:
//   ① BR 从 64 降到 8,workgroup 数 = N/8 × n_head。N=8192,H=4 ⇒ 4096 个 workgroup。
//   ② 累加器搬进 workgroup 共享内存,按 Dh 维切给 64 个线程,每线程只持有标量。
//   ③ head 走 dispatch 的 y 维,一次提交全部算完。
//   ④ 两个阶段的线程映射不同,各自都是满并行:
//        算 S:  64 线程分摊 BR×BC=192 个 (行,列) 对,每个串行点乘 Dh
//        算 O:  64 线程各管一个 Dh 维,每个对 BR×BC 求和
//
// 共享内存预算(WebGPU 硬上限 16384 B):
//   k_tile 24×64×4 = 6144  + v_tile 6144 + s 8×24×4 = 768 + acc 8×64×4 = 2048
//   + m/l 各 8×4 = 64  ⇒ 合计 15168 B,留 1.2KB 余量。

const BR : u32 = 8u;    // 每个 workgroup 负责的 query 行数
const BC : u32 = 24u;   // 每轮载入的 key/value 行数
const DH : u32 = 64u;   // head 维度(= workgroup_size)
const NEG_INF : f32 = -3.4028235e38;

struct Dims {
  n_q    : u32,
  n_kv   : u32,
  n_head : u32,
  _pad   : u32,
};

@group(0) @binding(0) var<storage, read>       Q : array<f32>;
@group(0) @binding(1) var<storage, read>       K : array<f32>;
@group(0) @binding(2) var<storage, read>       V : array<f32>;
@group(0) @binding(3) var<storage, read_write> O : array<f32>;
@group(0) @binding(4) var<uniform>             d : Dims;

var<workgroup> k_tile : array<f32, BC * DH>;
var<workgroup> v_tile : array<f32, BC * DH>;
var<workgroup> s      : array<f32, BR * BC>;
var<workgroup> acc    : array<f32, BR * DH>;
var<workgroup> m_run  : array<f32, BR>;
var<workgroup> l_run  : array<f32, BR>;
var<workgroup> resc   : array<f32, BR>;   // 每行本轮的重标定因子,阶段2算、阶段3用

fn idx(row : u32, head : u32, dh : u32, n_head : u32) -> u32 {
  return (row * n_head + head) * DH + dh;
}

@compute @workgroup_size(DH)
fn main(@builtin(workgroup_id) wg : vec3<u32>,
        @builtin(local_invocation_id) lid : vec3<u32>) {
  let head = wg.y;
  let q0 = wg.x * BR;
  let t = lid.x;                      // 0..63,既当 Dh 维号,也当分摊 (行,列) 的工号

  // ---- 初始化共享状态 ----
  for (var r = t; r < BR; r = r + DH) {
    m_run[r] = NEG_INF;
    l_run[r] = 0.0;
  }
  for (var i = t; i < BR * DH; i = i + DH) {
    acc[i] = 0.0;
  }
  workgroupBarrier();

  let scale = 1.0 / sqrt(f32(DH));

  var kv0 = 0u;
  loop {
    if (kv0 >= d.n_kv) { break; }
    let n_this = min(BC, d.n_kv - kv0);

    // ---- 协作载入 K/V 分块 ----
    for (var i = t; i < n_this * DH; i = i + DH) {
      let r = i / DH;
      let c = i % DH;
      let src = idx(kv0 + r, head, c, d.n_head);
      k_tile[i] = K[src];
      v_tile[i] = V[src];
    }
    workgroupBarrier();

    // ---- 阶段 1:64 线程分摊 BR×BC 个 logits,每个串行点乘 Dh ----
    for (var p = t; p < BR * n_this; p = p + DH) {
      let r = p / n_this;
      let j = p % n_this;
      let qrow = q0 + r;
      var dot : f32 = 0.0;
      if (qrow < d.n_q) {
        let qbase = idx(qrow, head, 0u, d.n_head);
        for (var i = 0u; i < DH; i = i + 1u) {
          dot = dot + Q[qbase + i] * k_tile[j * DH + i];
        }
      }
      s[r * BC + j] = select(NEG_INF, dot * scale, qrow < d.n_q);
    }
    workgroupBarrier();

    // ---- 阶段 2:每行的在线 softmax 重标定(BR 行,由前 BR 个线程各管一行)----
    if (t < BR) {
      var m_blk : f32 = NEG_INF;
      for (var j = 0u; j < n_this; j = j + 1u) {
        m_blk = max(m_blk, s[t * BC + j]);
      }
      let m_new = max(m_run[t], m_blk);
      var l_blk : f32 = 0.0;
      for (var j = 0u; j < n_this; j = j + 1u) {
        let p = exp(s[t * BC + j] - m_new);
        s[t * BC + j] = p;
        l_blk = l_blk + p;
      }
      // m_run 是上一轮的 max;重标定因子必须在覆写 m_run **之前**算好,
      // 并存进共享数组交给阶段 3 —— 那里 64 个线程要各自 rescale 自己那一维。
      let r_i = exp(m_run[t] - m_new);
      resc[t] = r_i;
      l_run[t] = l_run[t] * r_i + l_blk;
      m_run[t] = m_new;
    }
    workgroupBarrier();

    // ---- 阶段 3:每线程管一个 Dh 维,对 BR 行各自 rescale + 累加 ----
    for (var r = 0u; r < BR; r = r + 1u) {
      let qrow = q0 + r;
      if (qrow >= d.n_q) { continue; }
      var add : f32 = 0.0;
      for (var j = 0u; j < n_this; j = j + 1u) {
        add = add + s[r * BC + j] * v_tile[j * DH + t];
      }
      acc[r * DH + t] = acc[r * DH + t] * resc[r] + add;
    }
    workgroupBarrier();

    kv0 = kv0 + n_this;
  }

  // ---- 写回 ----
  for (var r = 0u; r < BR; r = r + 1u) {
    let qrow = q0 + r;
    if (qrow >= d.n_q) { continue; }
    let inv = select(0.0, 1.0 / l_run[r], l_run[r] > 0.0);
    O[idx(qrow, head, t, d.n_head)] = acc[r * DH + t] * inv;
  }
}
