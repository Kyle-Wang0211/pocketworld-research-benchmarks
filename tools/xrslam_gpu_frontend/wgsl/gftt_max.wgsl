@group(0) @binding(0) var<storage, read> eig: array<f32>;
@group(0) @binding(1) var<storage, read_write> partial: array<f32>;
@group(0) @binding(2) var<uniform> p: Params;
var<workgroup> sh: array<f32, 256>;
@compute @workgroup_size(256)
fn main(@builtin(global_invocation_id) gid: vec3<u32>, @builtin(local_invocation_id) lid: vec3<u32>, @builtin(workgroup_id) wg: vec3<u32>, @builtin(num_workgroups) nw: vec3<u32>) {
  let n = p.width * p.height; let stride = 256u * nw.x; var m = -3.4e38; var i = gid.x;
  loop { if (i >= n) { break; } m = max(m, eig[i]); i = i + stride; }
  sh[lid.x] = m; workgroupBarrier();
  for (var s = 128u; s > 0u; s = s >> 1u) { if (lid.x < s) { sh[lid.x] = max(sh[lid.x], sh[lid.x + s]); } workgroupBarrier(); }
  if (lid.x == 0u) { partial[wg.x] = sh[0]; }
}
