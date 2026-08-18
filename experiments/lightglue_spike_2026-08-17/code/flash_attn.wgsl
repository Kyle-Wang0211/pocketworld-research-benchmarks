// LightGlue 注意力的跨端融合 kernel(FlashAttention 式在线 softmax)。
//
// 为什么要它:LightGlue 的算力全在 9 层 × 4 个 N×N 注意力上。PyTorch/MPS 会把
// N×N 整个物化(8192 档 fp32 一张就 268MB,9 层累计撑爆),而且访存量是 O(N²)。
// 本 kernel 分块流式计算、**永不物化 N×N**,访存降到 O(N·Dh),把利用率从
// 实测的 ~35% 拉向 60%+。WGSL ⇒ iOS 走 Metal、Android 走 Vulkan、Web 走 WebGPU,
// 一份源码三端,不碰 CoreML/ANE 这类苹果专属物。
//
// 形状(LightGlue 固定):H = 4 头,Dh = 64,D = H*Dh = 256。
//   Q,K,V : [N, H, Dh]  行主序,行内按 head 连续
//   O     : [N, H, Dh]
//
// 数值口径:与 F.scaled_dot_product_attention 相同 —— scale = 1/sqrt(Dh),
// softmax 沿 key 维,fp32 累加。在线 softmax 的 max/sum 重标定是**代数恒等**,
// 不是近似:任何分块顺序下结果都等于全矩阵 softmax(浮点求和次序不同会有 ULP 级差异)。
//
// ⚠️ 分块尺寸受 WebGPU 的 maxComputeWorkgroupStorageSize = 16384 B 硬约束。
//    K_tile + V_tile = 2 * BC * Dh * 4B,取 BC = 32 正好 16384 B —— 贴死上限,
//    部分实现会为内建变量再留几十字节 ⇒ 取 BC = 24 留余量(见下方常量)。

const BR : u32 = 64u;   // 每个 workgroup 负责的 query 行数(= workgroup_size.x)
const BC : u32 = 24u;   // 每轮载入的 key/value 行数
const DH : u32 = 64u;   // head 维度
const NEG_INF : f32 = -3.4028235e38;

struct Dims {
  n_q   : u32,          // query 行数
  n_kv  : u32,          // key/value 行数(自注意力时 = n_q)
  n_head: u32,          // = 4
  head  : u32,          // 本次 dispatch 处理的 head 下标
};

@group(0) @binding(0) var<storage, read>       Q : array<f32>;
@group(0) @binding(1) var<storage, read>       K : array<f32>;
@group(0) @binding(2) var<storage, read>       V : array<f32>;
@group(0) @binding(3) var<storage, read_write> O : array<f32>;
@group(0) @binding(4) var<uniform>             d : Dims;

var<workgroup> k_tile : array<f32, BC * DH>;
var<workgroup> v_tile : array<f32, BC * DH>;

// [row, head, dh] → 线性下标
fn idx(row : u32, head : u32, dh : u32, n_head : u32) -> u32 {
  return (row * n_head + head) * DH + dh;
}

@compute @workgroup_size(BR)
fn main(@builtin(workgroup_id) wg : vec3<u32>,
        @builtin(local_invocation_id) lid : vec3<u32>) {
  let q_row = wg.x * BR + lid.x;
  let valid = q_row < d.n_q;

  // ---- Q 常驻寄存器;越界线程仍要参与 workgroupBarrier,只是不写回 ----
  var q : array<f32, DH>;
  if (valid) {
    for (var i = 0u; i < DH; i = i + 1u) {
      q[i] = Q[idx(q_row, d.head, i, d.n_head)];
    }
  }

  // ---- 在线 softmax 的running 状态 ----
  var acc : array<f32, DH>;
  for (var i = 0u; i < DH; i = i + 1u) { acc[i] = 0.0; }
  var m_run : f32 = NEG_INF;   // running max
  var l_run : f32 = 0.0;       // running sum(exp)

  let scale = 1.0 / sqrt(f32(DH));

  var kv0 = 0u;
  loop {
    if (kv0 >= d.n_kv) { break; }
    let n_this = min(BC, d.n_kv - kv0);

    // ---- 协作载入 K/V 分块到 workgroup 内存 ----
    // BR(64)个线程搬 BC*DH(24*64=1536)个元素,每线程 24 个
    workgroupBarrier();
    var t = lid.x;
    loop {
      if (t >= n_this * DH) { break; }
      let r = t / DH;
      let c = t % DH;
      let src = idx(kv0 + r, d.head, c, d.n_head);
      k_tile[t] = K[src];
      v_tile[t] = V[src];
      t = t + BR;
    }
    workgroupBarrier();

    if (valid) {
      // ---- 本块的 logits,并就地做在线重标定 ----
      var s : array<f32, BC>;
      var m_blk : f32 = NEG_INF;
      for (var j = 0u; j < n_this; j = j + 1u) {
        var dot : f32 = 0.0;
        for (var i = 0u; i < DH; i = i + 1u) {
          dot = dot + q[i] * k_tile[j * DH + i];
        }
        let sv = dot * scale;
        s[j] = sv;
        m_blk = max(m_blk, sv);
      }

      let m_new = max(m_run, m_blk);
      // 旧累加量按新 max 重标定 —— 这一步是代数恒等,不引入近似
      let rescale = exp(m_run - m_new);
      var l_blk : f32 = 0.0;
      for (var j = 0u; j < n_this; j = j + 1u) {
        let p = exp(s[j] - m_new);
        s[j] = p;
        l_blk = l_blk + p;
      }
      for (var i = 0u; i < DH; i = i + 1u) {
        var add : f32 = 0.0;
        for (var j = 0u; j < n_this; j = j + 1u) {
          add = add + s[j] * v_tile[j * DH + i];
        }
        acc[i] = acc[i] * rescale + add;
      }
      l_run = l_run * rescale + l_blk;
      m_run = m_new;
    }

    kv0 = kv0 + n_this;
  }

  if (valid) {
    // l_run 为 0 只可能出现在 n_kv==0(LightGlue 有零关键点的分支会提前返回),
    // 这里仍然兜一下,避免 NaN 顺着 9 层传播下去
    let inv = select(0.0, 1.0 / l_run, l_run > 0.0);
    for (var i = 0u; i < DH; i = i + 1u) {
      O[idx(q_row, d.head, i, d.n_head)] = acc[i] * inv;
    }
  }
}
