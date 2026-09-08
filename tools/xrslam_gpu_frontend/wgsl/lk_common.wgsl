// Shared by the M2/M3 kernels. Images are PACKED u8 (4 px per u32), stored PADDED:
// (pw = w + 2*pad) x (ph = h + 2*pad) with the level image at offset (pad, pad) — the exact layout
// OpenCV 4.0.1 buildOpticalFlowPyramid produces (winSize border 21, REFLECT_101|ISOLATED for the
// image, CONSTANT 0 for the Scharr derivative).
struct P {
  w: u32, h: u32, pw: u32, ph: u32,          // this level (interior / padded)
  w2: u32, h2: u32, pw2: u32, ph2: u32,      // next level (pyrdown target)
  tiles_x: u32, tiles_y: u32, tw: u32, th: u32,   // CLAHE
  inv_tw: f32, inv_th: f32, lut_scale: f32, clip: u32,
  base: u32, base2: u32, dbase: u32, pwq: u32,   // base: word offset of this level in the packed-u8 pyramid; dbase: u32 offset in the deriv buffer; pwq: words per padded row
  pwq2: u32, r0: u32, r1: u32, r2: u32,          // pwq2: words per padded row of the next level
};
// Packed image layout: one u32 holds 4 horizontally adjacent padded pixels (byte k = column 4*word+k). Derivatives: one u32 per
// pixel = (dx & 0xffff) | (dy << 16), i16 each. Writers own whole words (one thread per word) — no read-modify-write races.
fn ld8(buf_word: u32, x: u32) -> u32 { return (buf_word >> ((x & 3u) * 8u)) & 255u; }
const PAD: i32 = 21;
// cv::borderInterpolate(p, len, BORDER_REFLECT_101)
fn reflect101(p0: i32, len: i32) -> i32 {
  var p = p0;
  if (len == 1) { return 0; }
  loop {
    if (p < 0) { p = -p; }
    else if (p >= len) { p = len - 1 - (p - len) - 1; }
    else { break; }
  }
  return p;
}
