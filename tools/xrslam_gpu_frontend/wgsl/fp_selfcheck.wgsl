// Device floating-point primitive self-check. inp: 4 f32 per item (a in [0.5,2), b, c, d); outp: 12 f32 per item.
@group(0) @binding(0) var<storage, read> inp: array<f32>;
@group(0) @binding(1) var<storage, read_write> outp: array<f32>;
// Correctly rounded sqrt / division. The GPU's own sqrt/divide are not guaranteed correctly rounded (M3 sqrt: 26 % off by
// 1 ulp even in strict mode; A16 unknown). Start from the hardware result (within 1 ulp) and fix it with EXACT integer
// midpoint tests on the mantissas (64-bit arithmetic emulated with two u32).
fn mul64(a: u32, b: u32) -> vec2<u32> {   // a*b -> (lo, hi), a,b < 2^32
  let a0 = a & 0xffffu; let a1 = a >> 16u; let b0 = b & 0xffffu; let b1 = b >> 16u;
  let p00 = a0 * b0; let p01 = a0 * b1; let p10 = a1 * b0; let p11 = a1 * b1;
  let mid = (p00 >> 16u) + (p01 & 0xffffu) + (p10 & 0xffffu);
  let lo = (p00 & 0xffffu) | (mid << 16u);
  let hi = p11 + (p01 >> 16u) + (p10 >> 16u) + (mid >> 16u);
  return vec2<u32>(lo, hi);
}
fn shl64(m: u32, s: u32) -> vec2<u32> {   // m << s, s < 64
  if (s >= 32u) { return vec2<u32>(0u, m << (s - 32u)); }
  if (s == 0u) { return vec2<u32>(m, 0u); }
  return vec2<u32>(m << s, m >> (32u - s));
}
fn lt64(a: vec2<u32>, b: vec2<u32>) -> bool { return a.y < b.y || (a.y == b.y && a.x < b.x); }
fn ge64(a: vec2<u32>, b: vec2<u32>) -> bool { return !lt64(a, b); }
fn mant(f: f32) -> u32 { return (bitcast<u32>(f) & 0x7fffffu) | 0x800000u; }
fn expo(f: f32) -> i32 { return i32((bitcast<u32>(f) >> 23u) & 255u) - 127; }
// x = mx*2^(ex-23) (normal, > 0); candidate y = my*2^(ey-23). sqrt(x) >= y + ulp/2  <=>  x >= (2my+1)^2 * 2^(2ey-48)
//   <=> mx * 2^(ex - 2ey + 25) >= (2my+1)^2.   Likewise sqrt(x) < y - ulp/2 <=> mx * 2^(ex-2ey+25) < (2my-1)^2.
fn sqrt_rn(x: f32) -> f32 {
  var y = sqrt(x);
  if (!(x > 0.0) || y <= 0.0 || expo(x) < -120 || expo(x) > 120) { return y; }
  for (var it = 0; it < 2; it++) {
    let my = mant(y); let s = expo(x) - 2 * expo(y) + 25;
    if (s < 0 || s > 40) { return y; }
    let X = shl64(mant(x), u32(s));
    let up = mul64(2u * my + 1u, 2u * my + 1u); let dn = mul64(2u * my - 1u, 2u * my - 1u);
    if (ge64(X, up)) { y = bitcast<f32>(bitcast<u32>(y) + 1u); continue; }
    if (lt64(X, dn)) { y = bitcast<f32>(bitcast<u32>(y) - 1u); continue; }
    break;
  }
  return y;
}
// q = a/d (a,d > 0 normal): a/d >= q + ulp/2  <=>  ma*2^(ea-23) >= (2mq+1)*2^(eq-24) * md*2^(ed-23)
//   <=> ma * 2^(ea - eq - ed + 24) >= (2mq+1)*md ;  a/d < q - ulp/2 <=> ma * 2^(...) < (2mq-1)*md
fn div_rn_pos(a: f32, d: f32) -> f32 {
  var q = a / d;
  if (!(a > 0.0) || !(d > 0.0) || !(q > 0.0) || expo(a) < -120 || expo(a) > 120 || expo(d) < -120 || expo(d) > 120) { return q; }
  for (var it = 0; it < 2; it++) {
    let mq = mant(q); let s = expo(a) - expo(q) - expo(d) + 24;
    if (s < 0 || s > 40) { return q; }
    let Aa = shl64(mant(a), u32(s));
    let up = mul64(2u * mq + 1u, mant(d)); let dn = mul64(2u * mq - 1u, mant(d));
    if (ge64(Aa, up)) { q = bitcast<f32>(bitcast<u32>(q) + 1u); continue; }
    if (lt64(Aa, dn)) { q = bitcast<f32>(bitcast<u32>(q) - 1u); continue; }
    break;
  }
  return q;
}
fn div_rn(a: f32, d: f32) -> f32 {
  let neg = (a < 0.0) != (d < 0.0);
  let r = div_rn_pos(abs(a), abs(d));
  return select(r, -r, neg);
}
@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let i = gid.x; let o = i * 4u; let O = i * 14u;
  let a = inp[o]; let b = inp[o + 1u]; let c = inp[o + 2u]; let d = inp[o + 3u];
  let ia = i32(a * 65536.0 * 500.0);            // ~ up to 2^25: exercises int->float rounding
  outp[O + 0u] = 1.0 / a;                  // division
  outp[O + 1u] = sqrt(a);                  // sqrt
  outp[O + 2u] = f32(ia * 3 + 1);          // int->float (large, needs rounding)
  outp[O + 3u] = fma(a, b, 0.0) + fma(c, d, 0.0);   // guarded mul-add (no contraction)
  outp[O + 4u] = round(a * 8.0 + 0.5);     // ties (a*8 is exact-ish) -> half-even?
  outp[O + 5u] = a * b;                    // single multiply
  outp[O + 6u] = a + b;                    // single add
  outp[O + 7u] = (fma(a, b, 0.0) - fma(c, d, 0.0)) * (1.0 / (a + 1.0));   // LK delta shape
  outp[O + 8u] = floor(a * 1000.0 - 0.5);  // floor
  outp[O + 9u] = a * (1.0 / 1048576.0);    // FLT_SCALE multiply
  outp[O + 10u] = f32(i32(-(ia * 3 + 1)));  // negative int->float
  outp[O + 11u] = (a + b) * c - d * a;     // unguarded: contraction detector
  outp[O + 12u] = sqrt_rn(a);
  outp[O + 13u] = div_rn(1.0, a + 1.0);
}
