// APDe-MVS → WGSL:binding 契约
//
// ⚠️ 为什么单独一个文件:naga 实测报错
//     "Argument 'packed_maps' is a pointer of space Storage,
//      which can't be passed into functions."
//    WGSL 不允许把 storage 指针当函数参数传(除非开
//    unrestricted_pointer_parameters 扩展,那会牺牲可移植性)。
//    ⇒ 共享函数只能直接引用模块级 binding。
//    ⇒ **binding 布局是共享层的契约,不是调用方的自由。**
//    这条与 C5(binding 转译期冻结)是同一件事的两面。
//
// 拼接顺序必须是:common → bindings → geom → ncc → <entry>
//
// C1 复核:storage buffer 计数(iOS 每 stage 上限约 10)
//   1 cams  2 packed_maps  3 plane_hypotheses  4 costs  5 selected_views
//   6 rand_states  7 anchors  8 anchors_map          = 8 个 ✅ 在预算内
//   (原版 14 个 —— 靠 packed_maps 把 4 张 uchar 图并成 1 个省下来的)
//
// C2 复核:此处不出现任何数组长度查询,长度一律走 Params。

@group(0) @binding(0) var<uniform>                  P                 : Params;
@group(0) @binding(1) var<storage, read>            cams              : array<Camera, 32>;
// ⚠️ read_write 而非 read:C1 把 4 张 uchar 图打进一个 buffer 后,
//    ConfidenceCompute/DepthToWeak 等要写 confidence/weak_info 位段,
//    而 NCC 要读 sa_mask 位段 —— 同一个 buffer 既读又写。
//    ⚠️ 连带风险:不同位段的读写必须落在不同 dispatch,否则同一 dispatch 内
//       没有顺序保证。产品化时要在 pass 划分上把这条写进契约。
@group(0) @binding(2) var<storage, read_write>      packed_maps       : array<u32>;
@group(0) @binding(3) var<storage, read_write>      plane_hypotheses  : array<vec4<f32>>;
@group(0) @binding(4) var<storage, read_write>      costs             : array<f32>;
@group(0) @binding(5) var<storage, read_write>      selected_views    : array<u32>;
@group(0) @binding(6) var<storage, read_write>      rand_states       : array<u32>;
@group(0) @binding(7) var<storage, read>            anchors           : array<vec2<i32>>;
@group(0) @binding(8) var<storage, read>            anchors_map       : array<i32>;
// view_weight_cuda[center*MAX_IMAGES + i],原版是 uchar ⇒ 4 个打进 1 个 u32,
// 每像素 8 个 u32 = 32 B/px,与原版内存占用一致。
@group(0) @binding(9) var<storage, read_write>      view_weights_buf  : array<u32>;
// weak_nearest_strong:原版 short2,这里用 u32 打包(高 16 位 y,低 16 位 x)
@group(0) @binding(10) var<storage, read_write>     weak_nearest_buf  : array<u32>;
// anchors:原版 short2[anchors_map[center]*ANCHOR_NUM + i],这里 u32 打包
// (高 16 位 y,低 16 位 x;(-1,-1) 存为 0xFFFFFFFF)
@group(0) @binding(11) var<storage, read_write>     anchors_out       : array<u32>;

// C5:刻意用分离的 texture + sampler,不用 combined image sampler ——
//     combined 在 MSL 里必须拆成两个 binding,分离就没有 remap 歧义。
@group(1) @binding(0) var ref_tex : texture_2d<f32>;
@group(1) @binding(1) var src_tex : texture_2d<f32>;
@group(1) @binding(2) var samp    : sampler;
// 深度图:原版是 texture_depths_cuda[0].images[src_idx],即一组深度纹理。
// WGSL 用 texture_2d_array 表达同一件事(数组层 = src_idx)。
@group(1) @binding(3) var depth_tex    : texture_2d_array<f32>;
// ⚠️ 深度图必须最近邻取样(原版 (int)x+0.5f),双线性会在深度不连续处造假值
@group(1) @binding(4) var samp_nearest : sampler;

// view_weights 打包:4 个 uchar 一个 u32
fn vw_get(center : u32, i : u32) -> f32 {
  let w = view_weights_buf[center * 8u + (i >> 2u)];
  return f32((w >> ((i & 3u) * 8u)) & 0xFFu);
}
