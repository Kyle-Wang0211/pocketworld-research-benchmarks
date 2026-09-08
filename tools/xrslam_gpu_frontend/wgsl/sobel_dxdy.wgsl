// cv::Sobel(8U→32F, ksize 3, scale, BORDER_REFLECT_101) exactly as OpenCV 4.0.1 filter.cpp small filters evaluate it:
//  Dx: row anti-symmetric [-1,0,1] (kx[0]==0&&kx[1]==1 branch): S[+1]-S[-1]; column symmetric [1,2,1]*scale (generic): (S0+S2)*f1 + S1*f0, f0=2s f1=s
//  Dy: row symmetric [1,2,1]*scale (generic): S[0]*k0 + (S[-1]+S[+1])*k1, k0=2s k1=s; column anti-symmetric [-1,0,1] (is_m1_0_1): S2-S0
@group(0) @binding(0) var<storage, read> img: array<u32>;
@group(0) @binding(1) var<storage, read_write> dx: array<f32>;
@group(0) @binding(2) var<storage, read_write> dy: array<f32>;
@group(0) @binding(3) var<uniform> p: Params;
fn px(x: i32, y: i32) -> f32 { let xx = reflect101(x, i32(p.width)); let yy = reflect101(y, i32(p.height)); let c = u32(xx + 21); return f32((img[p.base + u32(yy + 21) * p.pwq + (c >> 2u)] >> ((c & 3u) * 8u)) & 255u); }   // packed padded layout (same buffer as the LK pyramid)
fn row_dx(x: i32, y: i32) -> f32 { return px(x + 1, y) - px(x - 1, y); }
fn row_dy(x: i32, y: i32, s: f32) -> f32 { return (fma(px(x - 1, y), s, 0.0) + fma(px(x, y), 2.0 * s, 0.0)) + fma(px(x + 1, y), s, 0.0); }   // generic RowFilter<uchar,float>: ((k0*S0 + k1*S1) + k2*S2), verified 0 mismatches vs 4.0.1
@compute @workgroup_size(16, 16)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
  if (gid.x >= p.width || gid.y >= p.height) { return; }
  let x = i32(gid.x); let y = i32(gid.y); let s = p.scale; let h = i32(p.height);
  let ym = reflect101(y - 1, h); let yp = reflect101(y + 1, h);
  dx[gid.y * p.width + gid.x] = fma(row_dx(x, ym) + row_dx(x, yp), s, fma(row_dx(x, y), 2.0 * s, 0.0));   // SymmColumnSmallVec_32f: v_muladd(S0+S2, k1, S1*k0) is vfmaq_f32 on arm64 (FUSED) — verified 0 mismatches vs 4.0.1
  dy[gid.y * p.width + gid.x] = row_dy(x, yp, s) - row_dy(x, ym, s);
}
