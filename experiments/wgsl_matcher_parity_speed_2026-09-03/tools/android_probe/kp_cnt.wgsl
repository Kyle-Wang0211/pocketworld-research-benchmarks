enable f16;

const INV_SQ_NORM : f32 = 0.000003814697265625; // 1/262144
const WGR : u32 = 32u;
const BT : u32 = 32u;
const KD : u32 = 128u;

struct Params {
  numA : u32,
  numB : u32,
  maxRatio : f32,
  maxDistance : f32,
  numWg : u32,
  rowBase : u32,
  colBase : u32,
  colSpan : u32,
};

struct ColPart {
  best : f32,
  second : f32,
  idx : i32,
};

@group(0) @binding(0) var<storage, read> A : array<u32>;
@group(0) @binding(1) var<storage, read> B : array<u32>;
@group(0) @binding(2) var<storage, read_write> OutAB : array<i32>;
@group(0) @binding(3) var<uniform> U : Params;
@group(0) @binding(4) var<storage, read_write> ColP : array<ColPart>;
@group(0) @binding(5) var<storage, read_write> OutBA : array<i32>;
@group(0) @binding(6) var<storage, read_write> RowP : array<ColPart>;
@group(0) @binding(7) var<storage, read> At : array<vec4<u32>>;
@group(0) @binding(8) var<storage, read> Bt : array<vec4<u32>>;

fn gatef(best : f32, second : f32, bestIndex : i32) -> i32 {
  if (bestIndex < 0) { return -1; }
  let bd = acos(min(best * INV_SQ_NORM, 1.0));
  let sd = acos(min(second * INV_SQ_NORM, 1.0));
  if (bd <= U.maxDistance && bd < U.maxRatio * sd) { return bestIndex; }
  return -1;
}

var<workgroup> P : array<u32, 1024>;

@compute @workgroup_size(64)
fn main(@builtin(workgroup_id) wg : vec3<u32>,
        @builtin(local_invocation_index) lid : u32) {
  let rb = U.rowBase + wg.x;
  let row0 = rb * WGR;
  let tr = lid / 8u;
  let tc = lid % 8u;
  let rowPad4 = ((U.numA + 31u) / 32u) * 8u;
  let colPad4 = ((U.numB + 127u) / 128u) * 32u;
  let rq = row0 / 4u + tr;

  let myRow = row0 + lid;
  var rowBest = 0.0;
  var rowSecond = 0.0;
  var rowBestI = -1;
  if (U.colBase != 0u && lid < WGR && myRow < U.numA) {
    let rp = RowP[myRow];
    rowBest = rp.best;
    rowSecond = rp.second;
    rowBestI = rp.idx;
  }

  var col0 = U.colBase;
  let colEnd = min(U.colBase + U.colSpan, U.numB);
  loop {
    if (col0 >= colEnd) { break; }
    let cq = col0 / 4u + tc;

    var acc0 = vec4<f32>(0.0);
    var acc1 = vec4<f32>(0.0);
    var acc2 = vec4<f32>(0.0);
    var acc3 = vec4<f32>(0.0);

    var ia = rq;
    var ib = cq;
    for (var k = KD; k != 0u; k = k - 2u) {
      let wb = Bt[ib];
      let wa = At[ia];
      let b4 = vec4<f32>(unpack2x16float(wb.x), unpack2x16float(wb.y));
      let al = vec4<f32>(unpack2x16float(wa.x), unpack2x16float(wa.y));
      acc0 = acc0 + al.x * b4;
      acc1 = acc1 + al.y * b4;
      acc2 = acc2 + al.z * b4;
      acc3 = acc3 + al.w * b4;
      let b4b = vec4<f32>(unpack2x16float(wb.z), unpack2x16float(wb.w));
      let alb = vec4<f32>(unpack2x16float(wa.z), unpack2x16float(wa.w));
      acc0 = acc0 + alb.x * b4b;
      acc1 = acc1 + alb.y * b4b;
      acc2 = acc2 + alb.z * b4b;
      acc3 = acc3 + alb.w * b4b;
      ia = ia + rowPad4;
      ib = ib + colPad4;
    }
    workgroupBarrier();
    {
      let cbase = tc * 4u;
      let rbase = tr * 4u;
      {
        let k0 = (u32(acc0.x) << 5u) | (31u - (cbase + 0u));
        let k1 = (u32(acc0.y) << 5u) | (31u - (cbase + 1u));
        let k2 = (u32(acc0.z) << 5u) | (31u - (cbase + 2u));
        let k3 = (u32(acc0.w) << 5u) | (31u - (cbase + 3u));
        var b = k0;
        var s = 0u;
        s = max(s, min(b, k1)); b = max(b, k1);
        s = max(s, min(b, k2)); b = max(b, k2);
        s = max(s, min(b, k3)); b = max(b, k3);
        P[((rbase + 0u) * 8u + tc) * 2u] = b;
        P[((rbase + 0u) * 8u + tc) * 2u + 1u] = s;
      }
      {
        let k0 = (u32(acc1.x) << 5u) | (31u - (cbase + 0u));
        let k1 = (u32(acc1.y) << 5u) | (31u - (cbase + 1u));
        let k2 = (u32(acc1.z) << 5u) | (31u - (cbase + 2u));
        let k3 = (u32(acc1.w) << 5u) | (31u - (cbase + 3u));
        var b = k0;
        var s = 0u;
        s = max(s, min(b, k1)); b = max(b, k1);
        s = max(s, min(b, k2)); b = max(b, k2);
        s = max(s, min(b, k3)); b = max(b, k3);
        P[((rbase + 1u) * 8u + tc) * 2u] = b;
        P[((rbase + 1u) * 8u + tc) * 2u + 1u] = s;
      }
      {
        let k0 = (u32(acc2.x) << 5u) | (31u - (cbase + 0u));
        let k1 = (u32(acc2.y) << 5u) | (31u - (cbase + 1u));
        let k2 = (u32(acc2.z) << 5u) | (31u - (cbase + 2u));
        let k3 = (u32(acc2.w) << 5u) | (31u - (cbase + 3u));
        var b = k0;
        var s = 0u;
        s = max(s, min(b, k1)); b = max(b, k1);
        s = max(s, min(b, k2)); b = max(b, k2);
        s = max(s, min(b, k3)); b = max(b, k3);
        P[((rbase + 2u) * 8u + tc) * 2u] = b;
        P[((rbase + 2u) * 8u + tc) * 2u + 1u] = s;
      }
      {
        let k0 = (u32(acc3.x) << 5u) | (31u - (cbase + 0u));
        let k1 = (u32(acc3.y) << 5u) | (31u - (cbase + 1u));
        let k2 = (u32(acc3.z) << 5u) | (31u - (cbase + 2u));
        let k3 = (u32(acc3.w) << 5u) | (31u - (cbase + 3u));
        var b = k0;
        var s = 0u;
        s = max(s, min(b, k1)); b = max(b, k1);
        s = max(s, min(b, k2)); b = max(b, k2);
        s = max(s, min(b, k3)); b = max(b, k3);
        P[((rbase + 3u) * 8u + tc) * 2u] = b;
        P[((rbase + 3u) * 8u + tc) * 2u + 1u] = s;
      }
      {
        let k0 = (u32(acc0.x) << 5u) | (31u - (rbase + 0u));
        let k1 = (u32(acc1.x) << 5u) | (31u - (rbase + 1u));
        let k2 = (u32(acc2.x) << 5u) | (31u - (rbase + 2u));
        let k3 = (u32(acc3.x) << 5u) | (31u - (rbase + 3u));
        var b = k0;
        var s = 0u;
        s = max(s, min(b, k1)); b = max(b, k1);
        s = max(s, min(b, k2)); b = max(b, k2);
        s = max(s, min(b, k3)); b = max(b, k3);
        P[512u + ((cbase + 0u) * 8u + tr) * 2u] = b;
        P[512u + ((cbase + 0u) * 8u + tr) * 2u + 1u] = s;
      }
      {
        let k0 = (u32(acc0.y) << 5u) | (31u - (rbase + 0u));
        let k1 = (u32(acc1.y) << 5u) | (31u - (rbase + 1u));
        let k2 = (u32(acc2.y) << 5u) | (31u - (rbase + 2u));
        let k3 = (u32(acc3.y) << 5u) | (31u - (rbase + 3u));
        var b = k0;
        var s = 0u;
        s = max(s, min(b, k1)); b = max(b, k1);
        s = max(s, min(b, k2)); b = max(b, k2);
        s = max(s, min(b, k3)); b = max(b, k3);
        P[512u + ((cbase + 1u) * 8u + tr) * 2u] = b;
        P[512u + ((cbase + 1u) * 8u + tr) * 2u + 1u] = s;
      }
      {
        let k0 = (u32(acc0.z) << 5u) | (31u - (rbase + 0u));
        let k1 = (u32(acc1.z) << 5u) | (31u - (rbase + 1u));
        let k2 = (u32(acc2.z) << 5u) | (31u - (rbase + 2u));
        let k3 = (u32(acc3.z) << 5u) | (31u - (rbase + 3u));
        var b = k0;
        var s = 0u;
        s = max(s, min(b, k1)); b = max(b, k1);
        s = max(s, min(b, k2)); b = max(b, k2);
        s = max(s, min(b, k3)); b = max(b, k3);
        P[512u + ((cbase + 2u) * 8u + tr) * 2u] = b;
        P[512u + ((cbase + 2u) * 8u + tr) * 2u + 1u] = s;
      }
      {
        let k0 = (u32(acc0.w) << 5u) | (31u - (rbase + 0u));
        let k1 = (u32(acc1.w) << 5u) | (31u - (rbase + 1u));
        let k2 = (u32(acc2.w) << 5u) | (31u - (rbase + 2u));
        let k3 = (u32(acc3.w) << 5u) | (31u - (rbase + 3u));
        var b = k0;
        var s = 0u;
        s = max(s, min(b, k1)); b = max(b, k1);
        s = max(s, min(b, k2)); b = max(b, k2);
        s = max(s, min(b, k3)); b = max(b, k3);
        P[512u + ((cbase + 3u) * 8u + tr) * 2u] = b;
        P[512u + ((cbase + 3u) * 8u + tr) * 2u + 1u] = s;
      }
    }
    workgroupBarrier();
    if (lid < WGR) {
      var b = 0u;
      var s = 0u;
      for (var t = 0u; t < 8u; t = t + 1u) {
        let bk = P[(lid * 8u + t) * 2u];
        let sk = P[(lid * 8u + t) * 2u + 1u];
        s = max(max(s, sk), min(b, bk));
        b = max(b, bk);
      }
      let b2 = f32(b >> 5u);
      let s2 = f32(s >> 5u);
      let i2 = select(i32(col0 + (31u - (b & 31u))), -1, (b >> 5u) == 0u);
      if (b2 > rowBest) { rowSecond = max(rowBest, s2); rowBest = b2; rowBestI = i2; }
      else { rowSecond = max(rowSecond, b2); }
    } else if (lid < WGR + 32u) {
      let c = lid - WGR;
      var b = 0u;
      var s = 0u;
      for (var t = 0u; t < 8u; t = t + 1u) {
        let bk = P[512u + (c * 8u + t) * 2u];
        let sk = P[512u + (c * 8u + t) * 2u + 1u];
        s = max(max(s, sk), min(b, bk));
        b = max(b, bk);
      }
      let cb = f32(b >> 5u);
      let cs = f32(s >> 5u);
      let ci = select(i32(row0 + (31u - (b & 31u))), -1, (b >> 5u) == 0u);
      let gc = col0 + c;
      if (gc < U.numB) { ColP[rb * U.numB + gc] = ColPart(cb, cs, ci); }
    }
    col0 = col0 + BT;
  }

  if (lid < WGR && myRow < U.numA) {
    RowP[myRow] = ColPart(rowBest, rowSecond, rowBestI);
    OutAB[myRow] = gatef(rowBest, rowSecond, rowBestI);
  }
}

@compute @workgroup_size(64)
fn merge(@builtin(global_invocation_id) gid : vec3<u32>) {
  let c = gid.x;
  if (c >= U.numB) { return; }
  var best = 0.0;
  var second = 0.0;
  var bi = -1;
  for (var w = 0u; w < U.numWg; w = w + 1u) {
    let p = ColP[w * U.numB + c];
    if (p.best > best) {
      second = max(best, p.second);
      best = p.best;
      bi = p.idx;
    } else {
      second = max(second, p.best);
    }
  }
  OutBA[c] = gatef(best, second, bi);
}

