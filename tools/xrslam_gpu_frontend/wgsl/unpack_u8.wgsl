// Packed contiguous u8 (already CLAHE'd) -> level-0 interior of the packed padded buffer. One thread per padded word.
@group(0) @binding(0) var<storage, read> src: array<u32>;
@group(0) @binding(1) var<storage, read_write> dst: array<u32>;
@group(0) @binding(2) var<uniform> p: P;
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let wq = gid.x; let py = gid.y;
  if (wq >= p.pwq || py >= p.ph) { return; }
  let yi = reflect101(i32(py) - PAD, i32(p.h));
  var word: u32 = 0u;
  for (var k: u32 = 0u; k < 4u; k++) {
    let xi = reflect101(i32(wq * 4u + k) - PAD, i32(p.w)); let i = u32(yi) * p.w + u32(xi);
    word |= ((src[i >> 2u] >> ((i & 3u) * 8u)) & 255u) << (k * 8u);
  }
  dst[p.base + py * p.pwq + wq] = word;
}
