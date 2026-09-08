// threshold = (float)(maxVal * qualityLevel): maxVal is the double from minMaxLoc (== the float max here), qualityLevel a double.
// One workgroup reduces the per-group partial maxima and forms the product with the double quality split as (q_hi + q_lo):
// p = mx*q_hi (rounded), e = exact error of that product, thr = p + (e + mx*q_lo) — the correctly rounded float of the
// double product except when the product lies within ~2^-53 of a float rounding boundary.
@group(0) @binding(0) var<storage, read> partial: array<f32>;
@group(0) @binding(1) var<storage, read_write> thr: array<f32>;
@group(0) @binding(2) var<uniform> qsplit: vec4<f32>;   // (q_hi, q_lo, 0, 0)
var<workgroup> sh: array<f32, 256>;
@compute @workgroup_size(256)
fn main(@builtin(local_invocation_index) lid: u32) {
  var m: f32 = -3.4e38;
  let n = arrayLength(&partial);
  for (var i: u32 = lid; i < n; i += 256u) { m = max(m, partial[i]); }
  sh[lid] = m;
  workgroupBarrier();
  for (var s: u32 = 128u; s > 0u; s >>= 1u) { if (lid < s) { sh[lid] = max(sh[lid], sh[lid + s]); } workgroupBarrier(); }
  if (lid == 0u) {
    let mx = sh[0];
    let pr = fma(mx, qsplit.x, 0.0); let e = fma(mx, qsplit.x, -pr);
    thr[0] = pr + (e + fma(mx, qsplit.y, 0.0));
  }
}
