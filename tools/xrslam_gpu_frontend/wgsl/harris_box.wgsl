// cov=(dx²,dx·dy,dy²) → 3×3 unnormalised box (RowSum then ColumnSum, BORDER_DEFAULT) → Harris: a*c - b*b - k*(a+c)*(a+c)  (calcHarris, corner.cpp)
@group(0) @binding(0) var<storage, read> dx: array<f32>;
@group(0) @binding(1) var<storage, read> dy: array<f32>;
@group(0) @binding(2) var<storage, read_write> eig: array<f32>;
@group(0) @binding(3) var<uniform> p: Params;
fn at(x: i32, y: i32) -> u32 { return u32(reflect101(y, i32(p.height))) * p.width + u32(reflect101(x, i32(p.width))); }
// boxFilter(cov, 3x3, normalize=false) on CV_32F sums in DOUBLE (RowSum<float,double>/ColumnSum<double,float>) and casts
// once: = the correctly rounded f32 of the exact 9-term sum. Emulated with a signed 96-bit fixed-point accumulator.
struct Acc { w0: u32, w1: u32, w2: u32 };
fn acc_add(a: ptr<function, Acc>, m: u32, sh: u32) {   // a += m << sh  (m < 2^24, sh < 96)
  let k = sh >> 5u; let b = sh & 31u;
  let lo = m << b; let hi = select(0u, m >> (32u - b), b != 0u);
  if (k == 0u) {
    let s0 = (*a).w0 + lo; let c0 = select(0u, 1u, s0 < lo); (*a).w0 = s0;
    let t1 = (*a).w1 + hi; let c1a = select(0u, 1u, t1 < hi); let s1 = t1 + c0; let c1b = select(0u, 1u, s1 < t1); (*a).w1 = s1;
    (*a).w2 = (*a).w2 + c1a + c1b;
  } else if (k == 1u) {
    let s1 = (*a).w1 + lo; let c1 = select(0u, 1u, s1 < lo); (*a).w1 = s1; (*a).w2 = (*a).w2 + hi + c1;
  } else { (*a).w2 = (*a).w2 + lo; }
}
fn acc_neg(a: ptr<function, Acc>) {   // two's complement negate
  let n0 = ~(*a).w0; let n1 = ~(*a).w1; let n2 = ~(*a).w2;
  let s0 = n0 + 1u; let c0 = select(0u, 1u, s0 == 0u); let s1 = n1 + c0; let c1 = select(0u, 1u, c0 == 1u && s1 == 0u);
  (*a).w0 = s0; (*a).w1 = s1; (*a).w2 = n2 + c1;
}
fn bit96(S: Acc, bit: i32) -> u32 { let w = select(select(S.w0, S.w1, bit >= 32), S.w2, bit >= 64); return (w >> u32(bit & 31)) & 1u; }
fn finish_sum(pos: Acc, neg0: Acc, base: i32) -> f32 {
  var neg = neg0; acc_neg(&neg);
  var S = pos;
  { let s0 = S.w0 + neg.w0; let c0 = select(0u, 1u, s0 < neg.w0); let t1 = S.w1 + neg.w1; let c1a = select(0u, 1u, t1 < neg.w1); let s1 = t1 + c0; let c1b = select(0u, 1u, s1 < t1); S.w0 = s0; S.w1 = s1; S.w2 = S.w2 + neg.w2 + c1a + c1b; }
  var negative = false;
  if ((S.w2 & 0x80000000u) != 0u) { negative = true; acc_neg(&S); }
  if (S.w0 == 0u && S.w1 == 0u && S.w2 == 0u) { return 0.0; }
  var hbit: i32;
  if (S.w2 != 0u) { hbit = 64 + 31 - i32(countLeadingZeros(S.w2)); } else if (S.w1 != 0u) { hbit = 32 + 31 - i32(countLeadingZeros(S.w1)); } else { hbit = 31 - i32(countLeadingZeros(S.w0)); }
  let lowbit = hbit - 23;
  var mant: u32; var guard: u32 = 0u; var sticky: u32 = 0u;
  if (lowbit <= 0) { mant = S.w0 << u32(-lowbit); }
  else {
    let lb = u32(lowbit); let k = lb >> 5u; let b = lb & 31u;
    let wk = select(select(S.w0, S.w1, k == 1u), S.w2, k == 2u); let wk1 = select(select(S.w1, S.w2, k == 1u), 0u, k == 2u);
    mant = select((wk >> b) | (wk1 << (32u - b)), wk, b == 0u) & 0xffffffu;
    let gb = lb - 1u; let gk = gb >> 5u; let gbit = gb & 31u; let wg = select(select(S.w0, S.w1, gk == 1u), S.w2, gk == 2u);
    guard = (wg >> gbit) & 1u;
    let below = wg & ((1u << gbit) - 1u);
    var st = below != 0u;
    if (gk >= 1u && S.w0 != 0u) { st = true; }
    if (gk >= 2u && S.w1 != 0u) { st = true; }
    sticky = select(0u, 1u, st);
  }
  if (guard == 1u && (sticky == 1u || (mant & 1u) == 1u)) { mant += 1u; }
  let e2 = (base - 127 - 23) + lowbit;
  let r = ldexp(f32(mant), e2);
  return select(r, -r, negative);
}
// Fast path: all 9 terms within 36 exponent steps -> the exact sum fits in 64 bits (24 + 36 + 4 carry) -> two-word accumulator.
fn sum9_fast(t0: f32, t1: f32, t2: f32, t3: f32, t4: f32, t5: f32, t6: f32, t7: f32, t8: f32, base: i32) -> f32 {
  var plo: u32 = 0u; var phi: u32 = 0u; var nlo: u32 = 0u; var nhi: u32 = 0u;
  { let b = bitcast<u32>(t0); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let sh = u32(ee - base);
      let lo = select(m << sh, 0u, sh >= 32u); let hi = select(select(m >> (32u - sh), 0u, sh == 0u), m << (sh - 32u), sh >= 32u);
      if ((b & 0x80000000u) != 0u) { let s = nlo + lo; nhi = nhi + hi + select(0u, 1u, s < lo); nlo = s; } else { let s = plo + lo; phi = phi + hi + select(0u, 1u, s < lo); plo = s; } } }
  { let b = bitcast<u32>(t1); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let sh = u32(ee - base);
      let lo = select(m << sh, 0u, sh >= 32u); let hi = select(select(m >> (32u - sh), 0u, sh == 0u), m << (sh - 32u), sh >= 32u);
      if ((b & 0x80000000u) != 0u) { let s = nlo + lo; nhi = nhi + hi + select(0u, 1u, s < lo); nlo = s; } else { let s = plo + lo; phi = phi + hi + select(0u, 1u, s < lo); plo = s; } } }
  { let b = bitcast<u32>(t2); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let sh = u32(ee - base);
      let lo = select(m << sh, 0u, sh >= 32u); let hi = select(select(m >> (32u - sh), 0u, sh == 0u), m << (sh - 32u), sh >= 32u);
      if ((b & 0x80000000u) != 0u) { let s = nlo + lo; nhi = nhi + hi + select(0u, 1u, s < lo); nlo = s; } else { let s = plo + lo; phi = phi + hi + select(0u, 1u, s < lo); plo = s; } } }
  { let b = bitcast<u32>(t3); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let sh = u32(ee - base);
      let lo = select(m << sh, 0u, sh >= 32u); let hi = select(select(m >> (32u - sh), 0u, sh == 0u), m << (sh - 32u), sh >= 32u);
      if ((b & 0x80000000u) != 0u) { let s = nlo + lo; nhi = nhi + hi + select(0u, 1u, s < lo); nlo = s; } else { let s = plo + lo; phi = phi + hi + select(0u, 1u, s < lo); plo = s; } } }
  { let b = bitcast<u32>(t4); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let sh = u32(ee - base);
      let lo = select(m << sh, 0u, sh >= 32u); let hi = select(select(m >> (32u - sh), 0u, sh == 0u), m << (sh - 32u), sh >= 32u);
      if ((b & 0x80000000u) != 0u) { let s = nlo + lo; nhi = nhi + hi + select(0u, 1u, s < lo); nlo = s; } else { let s = plo + lo; phi = phi + hi + select(0u, 1u, s < lo); plo = s; } } }
  { let b = bitcast<u32>(t5); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let sh = u32(ee - base);
      let lo = select(m << sh, 0u, sh >= 32u); let hi = select(select(m >> (32u - sh), 0u, sh == 0u), m << (sh - 32u), sh >= 32u);
      if ((b & 0x80000000u) != 0u) { let s = nlo + lo; nhi = nhi + hi + select(0u, 1u, s < lo); nlo = s; } else { let s = plo + lo; phi = phi + hi + select(0u, 1u, s < lo); plo = s; } } }
  { let b = bitcast<u32>(t6); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let sh = u32(ee - base);
      let lo = select(m << sh, 0u, sh >= 32u); let hi = select(select(m >> (32u - sh), 0u, sh == 0u), m << (sh - 32u), sh >= 32u);
      if ((b & 0x80000000u) != 0u) { let s = nlo + lo; nhi = nhi + hi + select(0u, 1u, s < lo); nlo = s; } else { let s = plo + lo; phi = phi + hi + select(0u, 1u, s < lo); plo = s; } } }
  { let b = bitcast<u32>(t7); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let sh = u32(ee - base);
      let lo = select(m << sh, 0u, sh >= 32u); let hi = select(select(m >> (32u - sh), 0u, sh == 0u), m << (sh - 32u), sh >= 32u);
      if ((b & 0x80000000u) != 0u) { let s = nlo + lo; nhi = nhi + hi + select(0u, 1u, s < lo); nlo = s; } else { let s = plo + lo; phi = phi + hi + select(0u, 1u, s < lo); plo = s; } } }
  { let b = bitcast<u32>(t8); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let sh = u32(ee - base);
      let lo = select(m << sh, 0u, sh >= 32u); let hi = select(select(m >> (32u - sh), 0u, sh == 0u), m << (sh - 32u), sh >= 32u);
      if ((b & 0x80000000u) != 0u) { let s = nlo + lo; nhi = nhi + hi + select(0u, 1u, s < lo); nlo = s; } else { let s = plo + lo; phi = phi + hi + select(0u, 1u, s < lo); plo = s; } } }
  // S = P - N (signed 64)
  var negative = false; var lo: u32; var hi: u32;
  if (phi > nhi || (phi == nhi && plo >= nlo)) { lo = plo - nlo; hi = phi - nhi - select(0u, 1u, plo < nlo); }
  else { negative = true; lo = nlo - plo; hi = nhi - phi - select(0u, 1u, nlo < plo); }
  if (lo == 0u && hi == 0u) { return 0.0; }
  var hbit: i32; if (hi != 0u) { hbit = 32 + 31 - i32(countLeadingZeros(hi)); } else { hbit = 31 - i32(countLeadingZeros(lo)); }
  let lowbit = hbit - 23;
  var mant: u32; var guard: u32 = 0u; var sticky: u32 = 0u;
  if (lowbit <= 0) { mant = lo << u32(-lowbit); }
  else {
    let lb = u32(lowbit);
    mant = select(select((lo >> lb) | (hi << (32u - lb)), lo, lb == 0u), hi >> (lb - 32u), lb >= 32u) & 0xffffffu;
    let gb = lb - 1u;
    guard = select((lo >> gb) & 1u, (hi >> (gb - 32u)) & 1u, gb >= 32u);
    let below_lo = select(lo & ((1u << gb) - 1u), lo, gb >= 32u);
    let below_hi = select(0u, hi & ((1u << (gb - 32u)) - 1u), gb >= 32u);
    sticky = select(0u, 1u, (below_lo | below_hi) != 0u);
  }
  if (guard == 1u && (sticky == 1u || (mant & 1u) == 1u)) { mant += 1u; }
  let r = ldexp(f32(mant), (base - 127 - 23) + lowbit);
  return select(r, -r, negative);
}
// Error-free fast path (Knuth TwoSum cascade, strict math: adds/subs only, no contraction possible). Accumulate s with
// TwoSum, feed every error into a second TwoSum accumulator e; if no error ever escapes the second level (all err2 == 0) then
// s + e is EXACTLY the real sum, and fl(s + e) is its correctly rounded float. Otherwise fall back to the integer path.
fn two_sum(a: f32, b: f32) -> vec2<f32> { let s = a + b; let bb = s - a; return vec2<f32>(s, (a - (s - bb)) + (b - bb)); }
fn sum9_ef(t0: f32, t1: f32, t2: f32, t3: f32, t4: f32, t5: f32, t6: f32, t7: f32, t8: f32) -> vec2<f32> {   // (result, ok)
  var s = t0; var e: f32 = 0.0; var lost: f32 = 0.0;
  { let r = two_sum(s, t1); s = r.x; let q = two_sum(e, r.y); e = q.x; lost += abs(q.y); }
  { let r = two_sum(s, t2); s = r.x; let q = two_sum(e, r.y); e = q.x; lost += abs(q.y); }
  { let r = two_sum(s, t3); s = r.x; let q = two_sum(e, r.y); e = q.x; lost += abs(q.y); }
  { let r = two_sum(s, t4); s = r.x; let q = two_sum(e, r.y); e = q.x; lost += abs(q.y); }
  { let r = two_sum(s, t5); s = r.x; let q = two_sum(e, r.y); e = q.x; lost += abs(q.y); }
  { let r = two_sum(s, t6); s = r.x; let q = two_sum(e, r.y); e = q.x; lost += abs(q.y); }
  { let r = two_sum(s, t7); s = r.x; let q = two_sum(e, r.y); e = q.x; lost += abs(q.y); }
  { let r = two_sum(s, t8); s = r.x; let q = two_sum(e, r.y); e = q.x; lost += abs(q.y); }
  return vec2<f32>(s + e, select(0.0, 1.0, lost == 0.0));
}
fn exact_sum9(t0: f32, t1: f32, t2: f32, t3: f32, t4: f32, t5: f32, t6: f32, t7: f32, t8: f32) -> f32 {
  var maxe: i32 = -1; var mine: i32 = 999;
  { let b = bitcast<u32>(t0); if ((b & 0x7fffffffu) != 0u) { let e = max(i32((b >> 23u) & 255u), 1); maxe = max(maxe, e); mine = min(mine, e); } }
  { let b = bitcast<u32>(t1); if ((b & 0x7fffffffu) != 0u) { let e = max(i32((b >> 23u) & 255u), 1); maxe = max(maxe, e); mine = min(mine, e); } }
  { let b = bitcast<u32>(t2); if ((b & 0x7fffffffu) != 0u) { let e = max(i32((b >> 23u) & 255u), 1); maxe = max(maxe, e); mine = min(mine, e); } }
  { let b = bitcast<u32>(t3); if ((b & 0x7fffffffu) != 0u) { let e = max(i32((b >> 23u) & 255u), 1); maxe = max(maxe, e); mine = min(mine, e); } }
  { let b = bitcast<u32>(t4); if ((b & 0x7fffffffu) != 0u) { let e = max(i32((b >> 23u) & 255u), 1); maxe = max(maxe, e); mine = min(mine, e); } }
  { let b = bitcast<u32>(t5); if ((b & 0x7fffffffu) != 0u) { let e = max(i32((b >> 23u) & 255u), 1); maxe = max(maxe, e); mine = min(mine, e); } }
  { let b = bitcast<u32>(t6); if ((b & 0x7fffffffu) != 0u) { let e = max(i32((b >> 23u) & 255u), 1); maxe = max(maxe, e); mine = min(mine, e); } }
  { let b = bitcast<u32>(t7); if ((b & 0x7fffffffu) != 0u) { let e = max(i32((b >> 23u) & 255u), 1); maxe = max(maxe, e); mine = min(mine, e); } }
  { let b = bitcast<u32>(t8); if ((b & 0x7fffffffu) != 0u) { let e = max(i32((b >> 23u) & 255u), 1); maxe = max(maxe, e); mine = min(mine, e); } }
  if (maxe < 0) { return 0.0; }
  { let r = sum9_ef(t0, t1, t2, t3, t4, t5, t6, t7, t8); if (r.y != 0.0) { return r.x; } }
  if (maxe - mine <= 36) { return sum9_fast(t0, t1, t2, t3, t4, t5, t6, t7, t8, mine); }
  var base = mine; if (maxe - mine > 71) { base = maxe - 64; }
  var pos = Acc(0u, 0u, 0u); var neg = Acc(0u, 0u, 0u);
  { let b = bitcast<u32>(t0); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let d = ee - base; if (d >= 0) { if ((b & 0x80000000u) != 0u) { acc_add(&neg, m, u32(d)); } else { acc_add(&pos, m, u32(d)); } } } }
  { let b = bitcast<u32>(t1); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let d = ee - base; if (d >= 0) { if ((b & 0x80000000u) != 0u) { acc_add(&neg, m, u32(d)); } else { acc_add(&pos, m, u32(d)); } } } }
  { let b = bitcast<u32>(t2); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let d = ee - base; if (d >= 0) { if ((b & 0x80000000u) != 0u) { acc_add(&neg, m, u32(d)); } else { acc_add(&pos, m, u32(d)); } } } }
  { let b = bitcast<u32>(t3); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let d = ee - base; if (d >= 0) { if ((b & 0x80000000u) != 0u) { acc_add(&neg, m, u32(d)); } else { acc_add(&pos, m, u32(d)); } } } }
  { let b = bitcast<u32>(t4); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let d = ee - base; if (d >= 0) { if ((b & 0x80000000u) != 0u) { acc_add(&neg, m, u32(d)); } else { acc_add(&pos, m, u32(d)); } } } }
  { let b = bitcast<u32>(t5); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let d = ee - base; if (d >= 0) { if ((b & 0x80000000u) != 0u) { acc_add(&neg, m, u32(d)); } else { acc_add(&pos, m, u32(d)); } } } }
  { let b = bitcast<u32>(t6); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let d = ee - base; if (d >= 0) { if ((b & 0x80000000u) != 0u) { acc_add(&neg, m, u32(d)); } else { acc_add(&pos, m, u32(d)); } } } }
  { let b = bitcast<u32>(t7); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let d = ee - base; if (d >= 0) { if ((b & 0x80000000u) != 0u) { acc_add(&neg, m, u32(d)); } else { acc_add(&pos, m, u32(d)); } } } }
  { let b = bitcast<u32>(t8); if ((b & 0x7fffffffu) != 0u) { let e = i32((b >> 23u) & 255u); var m = b & 0x7fffffu; var ee = e; if (e == 0) { ee = 1; } else { m |= 0x800000u; } let d = ee - base; if (d >= 0) { if ((b & 0x80000000u) != 0u) { acc_add(&neg, m, u32(d)); } else { acc_add(&pos, m, u32(d)); } } } }
  return finish_sum(pos, neg, base);
}
fn box3(x: i32, y: i32) -> vec3<f32> {
  let k0 = at(x - 1, y - 1); let k1 = at(x, y - 1); let k2 = at(x + 1, y - 1); let k3 = at(x - 1, y); let k4 = at(x, y); let k5 = at(x + 1, y); let k6 = at(x - 1, y + 1); let k7 = at(x, y + 1); let k8 = at(x + 1, y + 1);
  let a0 = dx[k0]; let a1 = dx[k1]; let a2 = dx[k2]; let a3 = dx[k3]; let a4 = dx[k4]; let a5 = dx[k5]; let a6 = dx[k6]; let a7 = dx[k7]; let a8 = dx[k8];
  let b0 = dy[k0]; let b1 = dy[k1]; let b2 = dy[k2]; let b3 = dy[k3]; let b4 = dy[k4]; let b5 = dy[k5]; let b6 = dy[k6]; let b7 = dy[k7]; let b8 = dy[k8];
  let sa = exact_sum9(fma(a0, a0, 0.0), fma(a1, a1, 0.0), fma(a2, a2, 0.0), fma(a3, a3, 0.0), fma(a4, a4, 0.0), fma(a5, a5, 0.0), fma(a6, a6, 0.0), fma(a7, a7, 0.0), fma(a8, a8, 0.0));
  let sb = exact_sum9(fma(a0, b0, 0.0), fma(a1, b1, 0.0), fma(a2, b2, 0.0), fma(a3, b3, 0.0), fma(a4, b4, 0.0), fma(a5, b5, 0.0), fma(a6, b6, 0.0), fma(a7, b7, 0.0), fma(a8, b8, 0.0));
  let sc = exact_sum9(fma(b0, b0, 0.0), fma(b1, b1, 0.0), fma(b2, b2, 0.0), fma(b3, b3, 0.0), fma(b4, b4, 0.0), fma(b5, b5, 0.0), fma(b6, b6, 0.0), fma(b7, b7, 0.0), fma(b8, b8, 0.0));
  return vec3<f32>(sa, sb, sc);
}
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  if (gid.x >= p.width || gid.y >= p.height) { return; }
  let x = i32(gid.x); let y = i32(gid.y);
  let c = box3(x, y);
  let a = c.x; let b = c.y; let cc = c.z;
  eig[gid.y * p.width + gid.x] = fma(a, cc, 0.0) - fma(b, b, 0.0) - fma(p.k * (a + cc), a + cc, 0.0);   // 4.0.1 calcHarris: a*c - b*b - k*(a+c)*(a+c), products guarded against FMA contraction
}
