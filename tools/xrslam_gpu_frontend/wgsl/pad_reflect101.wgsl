// copyMakeBorder(level, 21, BORDER_REFLECT_101 | BORDER_ISOLATED) on the packed layout. One thread per padded word; words that
// are fully interior are left untouched; mixed/border words are rebuilt byte by byte (interior bytes kept, border bytes reflected).
@group(0) @binding(0) var<storage, read_write> img: array<u32>;
@group(0) @binding(1) var<uniform> p: P;
fn px(x: i32, y: i32) -> u32 { let c = u32(x + PAD); return ld8(img[p.base + u32(y + PAD) * p.pwq + (c >> 2u)], c); }   // interior coords
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let wq = gid.x; let py = gid.y;
  if (wq >= p.pwq || py >= p.ph) { return; }
  let yi = i32(py) - PAD;
  let x0 = i32(wq * 4u) - PAD;
  let row_interior = yi >= 0 && yi < i32(p.h);
  if (row_interior && x0 >= 0 && x0 + 3 < i32(p.w)) { return; }   // fully interior word
  let idx = p.base + py * p.pwq + wq;
  let old = img[idx];
  var word: u32 = 0u;
  for (var k: u32 = 0u; k < 4u; k++) {
    let xi = x0 + i32(k);
    var v: u32;
    if (row_interior && xi >= 0 && xi < i32(p.w)) { v = (old >> (k * 8u)) & 255u; }
    else { v = px(reflect101(xi, i32(p.w)), reflect101(yi, i32(p.h))); }
    word |= v << (k * 8u);
  }
  img[idx] = word;
}
