// M1 — port of OpenCV 4.0.1 (c9ad5779, Apache-2.0) cornerHarris + goodFeaturesToTrack pieces.
// One thread per output pixel; arithmetic mirrors OpenCV's SymmRowSmallFilter / SymmColumnSmallFilter
// expression order (k0*x0 + k1*(x[-1]+x[1]) for symmetric, k1*(x[1]-x[-1]) for anti-symmetric),
// BORDER_REFLECT_101, float32.
struct Params { width: u32, height: u32, scale: f32, k: f32, quality: f32, max_corners: u32, pwq: u32, base: u32 };
fn reflect101(i: i32, n: i32) -> i32 { var j = i; if (j < 0) { j = -j; } if (j >= n) { j = 2 * n - 2 - j; } return j; }
