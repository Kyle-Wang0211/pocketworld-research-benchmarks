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
@group(0) @binding(7) var<storage, read> At : array<vec4<f16>>;
@group(0) @binding(8) var<storage, read> Bt : array<vec4<f16>>;

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

    var a0 = vec4<f32>(At[rq]);
    var a1 = vec4<f32>(At[rq + rowPad4]);
    var a2 = vec4<f32>(At[rq + 2u * rowPad4]);
    var a3 = vec4<f32>(At[rq + 3u * rowPad4]);
    var b0 = vec4<f32>(Bt[cq]);
    var b1 = vec4<f32>(Bt[cq + colPad4]);
    var b2 = vec4<f32>(Bt[cq + 2u * colPad4]);
    var b3 = vec4<f32>(Bt[cq + 3u * colPad4]);
    for (var k = 0u; k < KD; k = k + 4u) {
      acc0 = acc0 + vec4<f32>(dot(a0, b0), dot(a0, b1), dot(a0, b2), dot(a0, b3));
      acc1 = acc1 + vec4<f32>(dot(a1, b0), dot(a1, b1), dot(a1, b2), dot(a1, b3));
      acc2 = acc2 + vec4<f32>(dot(a2, b0), dot(a2, b1), dot(a2, b2), dot(a2, b3));
      acc3 = acc3 + vec4<f32>(dot(a3, b0), dot(a3, b1), dot(a3, b2), dot(a3, b3));
      a0 = a0.yzwx; a1 = a1.yzwx; a2 = a2.yzwx; a3 = a3.yzwx;
      b0 = b0.wxyz; b1 = b1.wxyz; b2 = b2.wxyz; b3 = b3.wxyz;
    }
    workgroupBarrier();
    {
      let cbase = tc * 4u;
      let rbase = tr * 4u;
      let colBits = vec4<u32>(31u - cbase, 30u - cbase, 29u - cbase, 28u - cbase);
      let u0 = vec4<u32>(acc0);
      let u1 = vec4<u32>(acc1);
      let u2 = vec4<u32>(acc2);
      let u3 = vec4<u32>(acc3);
      let r0 = (u0 << vec4<u32>(5u)) | colBits;
      let r1 = (u1 << vec4<u32>(5u)) | colBits;
      let r2 = (u2 << vec4<u32>(5u)) | colBits;
      let r3 = (u3 << vec4<u32>(5u)) | colBits;
      // 行 top-2:按列转置后 4 行同时折叠
      let tX = vec4<u32>(r0.x, r1.x, r2.x, r3.x);
      let tY = vec4<u32>(r0.y, r1.y, r2.y, r3.y);
      let tZ = vec4<u32>(r0.z, r1.z, r2.z, r3.z);
      let tW = vec4<u32>(r0.w, r1.w, r2.w, r3.w);
      let ra = max(tX, tY);
      let rb = min(tX, tY);
      let rc = max(tZ, tW);
      let rd = min(tZ, tW);
      let rbest = max(ra, rc);
      let rsec = max(min(ra, rc), max(rb, rd));
      P[((rbase + 0u) * 8u + tc) * 2u] = rbest.x;
      P[((rbase + 0u) * 8u + tc) * 2u + 1u] = rsec.x;
      P[((rbase + 1u) * 8u + tc) * 2u] = rbest.y;
      P[((rbase + 1u) * 8u + tc) * 2u + 1u] = rsec.y;
      P[((rbase + 2u) * 8u + tc) * 2u] = rbest.z;
      P[((rbase + 2u) * 8u + tc) * 2u + 1u] = rsec.z;
      P[((rbase + 3u) * 8u + tc) * 2u] = rbest.w;
      P[((rbase + 3u) * 8u + tc) * 2u + 1u] = rsec.w;
      // 列键:行位 31-rbase-i;列 top-2 直接按分量折叠(4 列同时)
      let c0 = (u0 << vec4<u32>(5u)) | vec4<u32>(31u - rbase);
      let c1 = (u1 << vec4<u32>(5u)) | vec4<u32>(30u - rbase);
      let c2 = (u2 << vec4<u32>(5u)) | vec4<u32>(29u - rbase);
      let c3 = (u3 << vec4<u32>(5u)) | vec4<u32>(28u - rbase);
      let ca = max(c0, c1);
      let cb_ = min(c0, c1);
      let cc = max(c2, c3);
      let cd = min(c2, c3);
      let cbest = max(ca, cc);
      let csec = max(min(ca, cc), max(cb_, cd));
      P[512u + ((cbase + 0u) * 8u + tr) * 2u] = cbest.x;
      P[512u + ((cbase + 0u) * 8u + tr) * 2u + 1u] = csec.x;
      P[512u + ((cbase + 1u) * 8u + tr) * 2u] = cbest.y;
      P[512u + ((cbase + 1u) * 8u + tr) * 2u + 1u] = csec.y;
      P[512u + ((cbase + 2u) * 8u + tr) * 2u] = cbest.z;
      P[512u + ((cbase + 2u) * 8u + tr) * 2u + 1u] = csec.z;
      P[512u + ((cbase + 3u) * 8u + tr) * 2u] = cbest.w;
      P[512u + ((cbase + 3u) * 8u + tr) * 2u + 1u] = csec.w;
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

