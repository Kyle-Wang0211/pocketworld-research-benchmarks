// findCorners (gftt.cl, 4.0.1): interior pixels (1..rows-2, 1..cols-2), val > threshold, strict 3×3 NMS (val == max of 9),
// atomic append of (val, packed y | x<<16). Threshold = maxEig * qualityLevel (host writes it into thr[0]).
@group(0) @binding(0) var<storage, read> eig: array<f32>;
@group(0) @binding(1) var<storage, read> thr: array<f32>;
@group(0) @binding(2) var<storage, read_write> count: atomic<u32>;
@group(0) @binding(3) var<storage, read_write> corners: array<vec2<u32>>;   // (bitcast<u32>(val), y | x<<16)
@group(0) @binding(4) var<uniform> p: Params;
fn e(x: u32, y: u32) -> f32 { return eig[y * p.width + x]; }
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let x = gid.x + 1u; let y = gid.y + 1u;
  if (x >= p.width - 1u || y >= p.height - 1u) { return; }
  let v = e(x, y);
  if (v > thr[0]) {
    var m = v;
    m = max(e(x-1u,y-1u), m); m = max(e(x,y-1u), m); m = max(e(x+1u,y-1u), m);
    m = max(e(x-1u,y), m);                          m = max(e(x+1u,y), m);
    m = max(e(x-1u,y+1u), m); m = max(e(x,y+1u), m); m = max(e(x+1u,y+1u), m);
    if (v == m) { let ind = atomicAdd(&count, 1u); if (ind < p.max_corners) { corners[ind] = vec2<u32>(bitcast<u32>(v), y | (x << 16u)); } }
  }
}
