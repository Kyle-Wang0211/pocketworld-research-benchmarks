// Sparse pyramidal LK, ONE WORKGROUP PER POINT. Same bit-for-bit semantics as lk_track.wgsl (OpenCV 4.0.1
// LKTrackerInvoker, arm64/NEON float accumulation order): the 441 bilinear samples / integer products are computed by
// 256 threads in parallel into workgroup memory; every float accumulation is done serially by thread 0 in NEON order
// (4 lanes for x<20 / int-paired 8-groups for x<16, scalar tails, lane sum ((0+1)+2)+3). Products feeding adds use fma(x,y,0.0).
struct LKP {
  n: u32, levels: u32, maxlevel: u32, flags: u32,
  lv: array<vec4<u32>, 4>,    // per level: (w, h, pw, base)
  dlv: array<vec4<u32>, 4>,   // per level: (w, h, pw, dbase)
};
@group(0) @binding(0) var<storage, read> I: array<u32>;
@group(0) @binding(1) var<storage, read> J: array<u32>;
@group(0) @binding(2) var<storage, read> dI: array<vec2<i32>>;
@group(0) @binding(3) var<storage, read> prevPts: array<vec2<f32>>;
@group(0) @binding(4) var<storage, read_write> nextPts: array<vec2<f32>>;
@group(0) @binding(5) var<storage, read_write> status: array<u32>;
@group(0) @binding(6) var<uniform> q: LKP;
const WIN: i32 = 21;
const NPIX: u32 = 441u;
const PADI: i32 = 21;
const HALF: f32 = 10.0;
const FLT_SCALE: f32 = 1.0 / 1048576.0;
const FLT_EPSILON: f32 = 1.1920929e-7;
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
fn descale(v: i32, n: u32) -> i32 { return (v + (1i << (n - 1u))) >> n; }
fn cvRound(x: f32) -> i32 { return i32(round(x)); }
fn cvFloor(x: f32) -> i32 { return i32(floor(x)); }
fn rdI(l: u32, x: i32, y: i32) -> i32 { return i32(I[q.lv[l].w + u32(y + PADI) * q.lv[l].z + u32(x + PADI)]); }
fn rdJ(l: u32, x: i32, y: i32) -> i32 { return i32(J[q.lv[l].w + u32(y + PADI) * q.lv[l].z + u32(x + PADI)]); }
fn rdD(l: u32, x: i32, y: i32) -> vec2<i32> { return dI[q.dlv[l].w + u32(y + PADI) * q.dlv[l].z + u32(x + PADI)]; }
fn weights(a: f32, b: f32) -> vec4<i32> {
  let iw00 = cvRound(fma((1.0 - a) * (1.0 - b), 16384.0, 0.0));
  let iw01 = cvRound(fma(a * (1.0 - b), 16384.0, 0.0));
  let iw10 = cvRound(fma((1.0 - a) * b, 16384.0, 0.0));
  return vec4<i32>(iw00, iw01, iw10, 16384 - iw00 - iw01 - iw10);
}
var<workgroup> IWin: array<i32, 441>;
var<workgroup> DIx: array<i32, 441>;
var<workgroup> DIy: array<i32, 441>;
var<workgroup> P1: array<i32, 441>;
var<workgroup> P2: array<i32, 441>;
var<workgroup> P3: array<i32, 441>;
var<workgroup> s_ipt: vec2<i32>;
var<workgroup> s_iw: vec4<i32>;
var<workgroup> s_flag: i32;       // 0 = go on, 1 = skip level, 2 = stop iterating
var<workgroup> s_nextPt: vec2<f32>;
var<workgroup> s_next: vec2<f32>;
var<workgroup> s_status: u32;
var<workgroup> s_A: vec3<f32>;
var<workgroup> s_D: f32;
var<workgroup> s_prevDelta: vec2<f32>;
@compute @workgroup_size(256)
fn main(@builtin(workgroup_id) wg: vec3<u32>, @builtin(local_invocation_index) lid: u32) {
  let idx = wg.x;
  if (idx >= q.n) { return; }
  if (lid == 0u) { s_status = 1u; s_next = nextPts[idx]; }
  workgroupBarrier();
  for (var lvl: i32 = i32(q.maxlevel); lvl >= 0; lvl--) {
    let l = u32(lvl);
    let cols = i32(q.lv[l].x); let rows = i32(q.lv[l].y);
    workgroupBarrier();
    if (lid == 0u) {
      let scale = 1.0 / f32(1i << u32(lvl));
      var prevPt = prevPts[idx] * scale;
      var nextPt: vec2<f32>;
      if (lvl == i32(q.maxlevel)) { nextPt = nextPts[idx] * scale; } else { nextPt = s_next * 2.0; }
      s_next = nextPt;
      s_nextPt = nextPt;
      prevPt = prevPt - vec2<f32>(HALF, HALF);
      let ipx = cvFloor(prevPt.x); let ipy = cvFloor(prevPt.y);
      s_ipt = vec2<i32>(ipx, ipy);
      if (ipx < -WIN || ipx >= cols || ipy < -WIN || ipy >= rows) { if (lvl == 0) { s_status = 0u; } s_flag = 1; }
      else { s_flag = 0; s_iw = weights(prevPt.x - f32(ipx), prevPt.y - f32(ipy)); }
    }
    workgroupBarrier(); let f0 = s_flag; workgroupBarrier();
    if (f0 == 1) { continue; }
    let ipx = s_ipt.x; let ipy = s_ipt.y; let iw = s_iw;
    for (var o: u32 = lid; o < NPIX; o += 256u) {
      let y = i32(o / 21u); let x = i32(o % 21u); let sx = ipx + x; let sy = ipy + y;
      let v = descale(rdI(l, sx, sy) * iw.x + rdI(l, sx + 1, sy) * iw.y + rdI(l, sx, sy + 1) * iw.z + rdI(l, sx + 1, sy + 1) * iw.w, 9u);
      let d00 = rdD(l, sx, sy); let d01 = rdD(l, sx + 1, sy); let d10 = rdD(l, sx, sy + 1); let d11 = rdD(l, sx + 1, sy + 1);
      let ix = descale(d00.x * iw.x + d01.x * iw.y + d10.x * iw.z + d11.x * iw.w, 14u);
      let iy = descale(d00.y * iw.x + d01.y * iw.y + d10.y * iw.z + d11.y * iw.w, 14u);
      IWin[o] = v; DIx[o] = ix; DIy[o] = iy; P1[o] = ix * ix; P2[o] = ix * iy; P3[o] = iy * iy;
    }
    workgroupBarrier();
    if (lid == 0u) {
      var nA11 = vec4<f32>(0.0); var nA12 = vec4<f32>(0.0); var nA22 = vec4<f32>(0.0);
      var iA11: f32 = 0.0; var iA12: f32 = 0.0; var iA22: f32 = 0.0;
      for (var y: i32 = 0; y < WIN; y++) {
        for (var x: i32 = 0; x < WIN; x++) {
          let o = u32(y * WIN + x);
          if (x < 20) { let lane = x & 3; nA11[lane] += f32(P1[o]); nA12[lane] += f32(P2[o]); nA22[lane] += f32(P3[o]); }
          else { iA11 += f32(P1[o]); iA12 += f32(P2[o]); iA22 += f32(P3[o]); }
        }
      }
      iA11 += ((nA11.x + nA11.y) + nA11.z) + nA11.w;
      iA12 += ((nA12.x + nA12.y) + nA12.z) + nA12.w;
      iA22 += ((nA22.x + nA22.y) + nA22.z) + nA22.w;
      let A11 = iA11 * FLT_SCALE; let A12 = iA12 * FLT_SCALE; let A22 = iA22 * FLT_SCALE;
      let D = fma(A11, A22, 0.0) - fma(A12, A12, 0.0);
      let minEig = div_rn(A22 + A11 - sqrt_rn(fma(A11 - A22, A11 - A22, 0.0) + fma(4.0 * A12, A12, 0.0)), f32(2 * WIN * WIN));
      if (minEig < 1e-4 || D < FLT_EPSILON) { if (lvl == 0) { s_status = 0u; } s_flag = 1; }
      else { s_flag = 0; s_A = vec3<f32>(A11, A12, A22); s_D = div_rn(1.0, D); s_nextPt = s_nextPt - vec2<f32>(HALF, HALF); s_prevDelta = vec2<f32>(0.0, 0.0); }
    }
    workgroupBarrier(); let f1 = s_flag; workgroupBarrier();
    if (f1 == 1) { continue; }
    for (var j: i32 = 0; j < 30; j++) {
      workgroupBarrier();
      if (lid == 0u) {
        let inx = cvFloor(s_nextPt.x); let iny = cvFloor(s_nextPt.y);
        if (inx < -WIN || inx >= cols || iny < -WIN || iny >= rows) { if (lvl == 0) { s_status = 0u; } s_flag = 2; }
        else { s_flag = 0; s_ipt = vec2<i32>(inx, iny); s_iw = weights(s_nextPt.x - f32(inx), s_nextPt.y - f32(iny)); }
      }
      workgroupBarrier(); let f2 = s_flag; workgroupBarrier();
      if (f2 == 2) { break; }
      let inx = s_ipt.x; let iny = s_ipt.y; let jw = s_iw;
      for (var o: u32 = lid; o < NPIX; o += 256u) {
        let y = i32(o / 21u); let x = i32(o % 21u); let sx = inx + x; let sy = iny + y;
        let diff = descale(rdJ(l, sx, sy) * jw.x + rdJ(l, sx + 1, sy) * jw.y + rdJ(l, sx, sy + 1) * jw.z + rdJ(l, sx + 1, sy + 1) * jw.w, 9u) - IWin[o];
        P1[o] = diff * DIx[o]; P2[o] = diff * DIy[o];
      }
      workgroupBarrier();
      if (lid == 0u) {
        var nB1 = vec4<f32>(0.0); var nB2 = vec4<f32>(0.0);
        var ib1: f32 = 0.0; var ib2: f32 = 0.0;
        for (var y: i32 = 0; y < WIN; y++) {
          for (var g: i32 = 0; g < 16; g += 8) {
            var s1 = vec4<i32>(0); var s2 = vec4<i32>(0);
            for (var k: i32 = 0; k < 8; k++) { let o = u32(y * WIN + g + k); s1[k & 3] += P1[o]; s2[k & 3] += P2[o]; }
            nB1 += vec4<f32>(s1); nB2 += vec4<f32>(s2);
          }
          for (var x: i32 = 16; x < WIN; x++) { let o = u32(y * WIN + x); ib1 += f32(P1[o]); ib2 += f32(P2[o]); }
        }
        ib1 += ((nB1.x + nB1.y) + nB1.z) + nB1.w;
        ib2 += ((nB2.x + nB2.y) + nB2.z) + nB2.w;
        let b1 = ib1 * FLT_SCALE; let b2 = ib2 * FLT_SCALE;
        let A = s_A; let D = s_D;
        let delta = vec2<f32>((fma(A.y, b2, 0.0) - fma(A.z, b1, 0.0)) * D, (fma(A.y, b1, 0.0) - fma(A.x, b2, 0.0)) * D);
        s_nextPt = s_nextPt + delta;
        s_next = s_nextPt + vec2<f32>(HALF, HALF);
        if (dot(delta, delta) <= 1e-4) { s_flag = 2; }
        else if (j > 0 && abs(delta.x + s_prevDelta.x) < 0.01 && abs(delta.y + s_prevDelta.y) < 0.01) { s_next = s_next - delta * 0.5; s_flag = 2; }
        else { s_flag = 0; s_prevDelta = delta; }
      }
      workgroupBarrier(); let f3 = s_flag; workgroupBarrier();
      if (f3 == 2) { break; }
    }
  }
  workgroupBarrier();
  if (lid == 0u) { nextPts[idx] = s_next; status[idx] = s_status; }
}
