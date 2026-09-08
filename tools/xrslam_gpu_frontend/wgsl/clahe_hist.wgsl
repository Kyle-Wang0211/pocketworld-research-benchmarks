// CLAHE_CalcLut_Body part 1: per-tile 256-bin histogram (one workgroup per tile).
@group(0) @binding(0) var<storage, read> src: array<u32>;               // w*h interior, PACKED u8 (4 px per u32)
@group(0) @binding(1) var<storage, read_write> hist: array<atomic<u32>>; // tiles*256
@group(0) @binding(2) var<uniform> p: P;
var<workgroup> lh: array<atomic<u32>, 256>;
@compute @workgroup_size(256)
fn main(@builtin(local_invocation_index) lid: u32, @builtin(workgroup_id) wg: vec3<u32>) {
  atomicStore(&lh[lid], 0u);
  workgroupBarrier();
  let tx = wg.x; let ty = wg.y;
  let n = p.tw * p.th;
  for (var i: u32 = lid; i < n; i += 256u) {
    let x = tx * p.tw + (i % p.tw);
    let y = ty * p.th + (i / p.tw);
    let i = y * p.w + x;
    atomicAdd(&lh[(src[i >> 2u] >> ((i & 3u) * 8u)) & 255u], 1u);
  }
  workgroupBarrier();
  let tile = ty * p.tiles_x + tx;
  atomicStore(&hist[tile * 256u + lid], atomicLoad(&lh[lid]));
}
