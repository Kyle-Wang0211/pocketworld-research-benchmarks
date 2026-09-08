// calcSharrDeriv (4.0.1 lkpyramid.cpp): dx/dy as i16 pairs packed in one u32 per padded pixel ((dx & 0xffff) | (dy << 16));
// ring of 21 = 0 (derivBorder CONSTANT).
@group(0) @binding(0) var<storage, read> src: array<u32>;         // packed padded level
@group(0) @binding(1) var<storage, read_write> deriv: array<u32>; // one u32 per padded pixel at dbase, pitch pw
@group(0) @binding(2) var<uniform> pl: array<P, 4>;   // one P per level, z = level
var<private> p: P;
fn s(x: i32, y: i32) -> i32 {
  let c = u32(reflect101(x, i32(p.w)) + PAD);
  return i32(ld8(src[p.base + u32(reflect101(y, i32(p.h)) + PAD) * p.pwq + (c >> 2u)], c));
}
fn t0(x: i32, y: i32) -> i32 { return (s(x, y - 1) + s(x, y + 1)) * 3 + s(x, y) * 10; }
fn t1(x: i32, y: i32) -> i32 { return s(x, y + 1) - s(x, y - 1); }
@compute @workgroup_size(16, 16, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  p = pl[gid.z];
  let x = i32(gid.x); let y = i32(gid.y);
  if (x >= i32(p.pw) || y >= i32(p.ph)) { return; }
  let xi = x - PAD; let yi = y - PAD;
  let o = p.dbase + u32(y) * p.pw + u32(x);
  if (xi < 0 || yi < 0 || xi >= i32(p.w) || yi >= i32(p.h)) { deriv[o] = 0u; return; }
  let dx = t0(xi + 1, yi) - t0(xi - 1, yi);
  let dy = (t1(xi + 1, yi) + t1(xi - 1, yi)) * 3 + t1(xi, yi) * 10;
  deriv[o] = (u32(dx) & 0xffffu) | (u32(dy) << 16u);
}
