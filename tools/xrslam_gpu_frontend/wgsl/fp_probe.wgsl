@group(0) @binding(0) var<storage, read> inp: array<f32>;      // 10 floats per item
@group(0) @binding(1) var<storage, read_write> outp: array<f32>; // 6 per item
@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let i = gid.x; let o = i * 10u;
  let a = inp[o]; let b = inp[o+1u]; let c = inp[o+2u]; let d = inp[o+3u]; let e = inp[o+4u];
  let f = inp[o+5u]; let g = inp[o+6u]; let h = inp[o+7u]; let k = inp[o+8u]; let j = inp[o+9u];
  outp[i*6u] = a * b + c * d;                                   // r0 plain expression (compiler may contract)
  outp[i*6u+1u] = fma(a, b, 0.0) + fma(c, d, 0.0);              // r1 fma-zero guard
  outp[i*6u+2u] = bitcast<f32>(bitcast<u32>(a * b)) + bitcast<f32>(bitcast<u32>(c * d)); // r2 bitcast guard
  let t1 = fma(a, b, 0.0) + fma(c, d, 0.0); let t2 = fma(f, g, 0.0) + fma(h, k, 0.0);
  outp[i*6u+3u] = fma(t1, e, 0.0) + fma(t2, j, 0.0);            // r3 nested with guards
  outp[i*6u+4u] = round(a + 0.5);                               // r4 ties: a integer -> half-even?
  outp[i*6u+5u] = f32(u32(a) * 16777215u + u32(c));             // r5 u32->f32 conversion rounding
}
