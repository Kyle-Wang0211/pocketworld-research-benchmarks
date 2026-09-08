// Level-0 interior (packed padded) -> contiguous packed u8 (w*h bytes) for readback. One thread per output word.
@group(0) @binding(0) var<storage, read> img: array<u32>;
@group(0) @binding(1) var<storage, read_write> outp: array<u32>;
@group(0) @binding(2) var<uniform> p: P;
@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let n = p.w * p.h; let i4 = gid.x;
  if (i4 * 4u >= n) { return; }
  var word: u32 = 0u;
  for (var k: u32 = 0u; k < 4u; k++) {
    let i = i4 * 4u + k;
    if (i < n) { let x = i % p.w; let y = i / p.w; let c = x + u32(PAD); word |= ld8(img[p.base + (y + u32(PAD)) * p.pwq + (c >> 2u)], c) << (k * 8u); }
  }
  outp[i4] = word;
}
