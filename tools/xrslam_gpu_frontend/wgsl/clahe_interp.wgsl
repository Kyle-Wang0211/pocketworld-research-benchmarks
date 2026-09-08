// CLAHE_Interpolation_Body. Host-computed weight tables (colt per column, rowt per row), products guarded with fma(x,y,0.0).
// One thread per PADDED WORD of level 0: writes the 4 bytes of that word; border bytes are the interpolated value at the
// REFLECT_101 coordinate (== copyMakeBorder after the fact), so no pad pass is needed.
@group(0) @binding(0) var<storage, read> src: array<u32>;         // packed u8, w*h interior (unpadded)
@group(0) @binding(1) var<storage, read> lut: array<u32>;
@group(0) @binding(2) var<storage, read_write> dst: array<u32>;   // packed padded level 0 at base
@group(0) @binding(3) var<uniform> p: P;
@group(0) @binding(4) var<storage, read> colt: array<vec4<f32>>;  // per column: (ind1, ind2, xa, xa1)
@group(0) @binding(5) var<storage, read> rowt: array<vec4<f32>>;  // per row: (ty1*tilesX*256, ty2*tilesX*256, ya, ya1)
fn clahe_px(x: u32, y: u32) -> u32 {
  let ct = colt[x]; let rt = rowt[y];
  let i = y * p.w + x;
  let v = i32((src[i >> 2u] >> ((i & 3u) * 8u)) & 255u);
  let ind1 = i32(ct.x) + v; let ind2 = i32(ct.y) + v; let xa = ct.z; let xa1 = ct.w;
  let l1 = i32(rt.x); let l2 = i32(rt.y); let ya = rt.z; let ya1 = rt.w;
  let t1 = fma(f32(lut[l1 + ind1]), xa1, 0.0) + fma(f32(lut[l1 + ind2]), xa, 0.0);
  let t2 = fma(f32(lut[l2 + ind1]), xa1, 0.0) + fma(f32(lut[l2 + ind2]), xa, 0.0);
  let res = fma(t1, ya1, 0.0) + fma(t2, ya, 0.0);
  return u32(clamp(round(res), 0.0, 255.0));
}
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let wq = gid.x; let py = gid.y;                  // padded word column, padded row
  if (wq >= p.pwq || py >= p.ph) { return; }
  let yi = reflect101(i32(py) - PAD, i32(p.h));   // border bytes = REFLECT_101 of the interior (the pad pass, fused)
  var word: u32 = 0u;
  for (var k: u32 = 0u; k < 4u; k++) {
    let xi = reflect101(i32(wq * 4u + k) - PAD, i32(p.w));
    word |= clahe_px(u32(xi), u32(yi)) << (k * 8u);
  }
  dst[p.base + py * p.pwq + wq] = word;
}
