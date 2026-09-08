// CLAHE_CalcLut_Body part 2: clip, redistribute, cumulative LUT (one thread per tile; 4.0.1 clahe.cpp).
@group(0) @binding(0) var<storage, read> hist: array<u32>;
@group(0) @binding(1) var<storage, read_write> lut: array<u32>;
@group(0) @binding(2) var<uniform> p: P;
@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  let tile = gid.x;
  if (tile >= p.tiles_x * p.tiles_y) { return; }
  var th: array<i32, 256>;
  for (var i: u32 = 0u; i < 256u; i++) { th[i] = i32(hist[tile * 256u + i]); }
  if (p.clip > 0u) {
    let clip = i32(p.clip);
    var clipped: i32 = 0;
    for (var i: u32 = 0u; i < 256u; i++) {
      if (th[i] > clip) { clipped += th[i] - clip; th[i] = clip; }
    }
    let redistBatch = clipped / 256;
    var residual = clipped - redistBatch * 256;
    for (var i: u32 = 0u; i < 256u; i++) { th[i] += redistBatch; }
    if (residual != 0) {
      let residualStep = max(256 / residual, 1);
      var i: i32 = 0;
      loop {
        if (!(i < 256 && residual > 0)) { break; }
        th[i] += 1;
        i += residualStep; residual -= 1;
      }
    }
  }
  var sum: i32 = 0;
  for (var i: u32 = 0u; i < 256u; i++) {
    sum += th[i];
    let v = round(f32(sum) * p.lut_scale);          // saturate_cast<uchar>(float): cvRound = lrint (half-even)
    lut[tile * 256u + i] = u32(clamp(v, 0.0, 255.0));
  }
}
