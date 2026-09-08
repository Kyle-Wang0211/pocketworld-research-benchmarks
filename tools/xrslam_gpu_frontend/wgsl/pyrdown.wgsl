// pyrDown_<FixPtCast<uchar,8>, PyrDownNoVec<int,uchar>> cn=1, BORDER_REFLECT_101 (4.0.1 pyramids.cpp), packed layout.
// One thread per padded word of level l+1; border bytes reflected (no pad pass).
@group(0) @binding(0) var<storage, read_write> img: array<u32>;   // reads level l (base, pwq), writes level l+1 (base2, pwq2)
@group(0) @binding(1) var<uniform> p: P;
fn s(x: i32, y: i32) -> i32 {
  let c = u32(reflect101(x, i32(p.w)) + PAD);
  return i32(ld8(img[p.base + u32(reflect101(y, i32(p.h)) + PAD) * p.pwq + (c >> 2u)], c));
}
fn row(y: i32, x: i32) -> i32 { return s(2 * x, y) * 6 + (s(2 * x - 1, y) + s(2 * x + 1, y)) * 4 + s(2 * x - 2, y) + s(2 * x + 2, y); }
fn down_px(x: i32, y: i32) -> u32 {
  let r0 = row(2 * y - 2, x); let r1 = row(2 * y - 1, x); let r2 = row(2 * y, x); let r3 = row(2 * y + 1, x); let r4 = row(2 * y + 2, x);
  return u32((r2 * 6 + (r1 + r3) * 4 + r0 + r4 + 128) >> 8u);
}
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let wq = gid.x; let py = gid.y;
  if (wq >= p.pwq2 || py >= p.ph2) { return; }
  let yi = reflect101(i32(py) - PAD, i32(p.h2));   // border bytes = REFLECT_101 of the level-(l+1) interior (pad pass fused)
  var word: u32 = 0u;
  for (var k: u32 = 0u; k < 4u; k++) {
    let xi = reflect101(i32(wq * 4u + k) - PAD, i32(p.w2));
    word |= down_px(xi, yi) << (k * 8u);
  }
  img[p.base2 + py * p.pwq2 + wq] = word;
}
