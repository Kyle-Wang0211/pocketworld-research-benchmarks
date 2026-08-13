#!/usr/bin/env bash
# APDe-MVS WGSL 移植:构建 + 打点
# 依赖:brew install naga-cli spirv-cross glslang  + Xcode(metal 编译器)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/apde_build}"
mkdir -p "$OUT"

# ⚠️ 拼接顺序是契约,不能改:common → bindings → geom → rand → geomcons → ncc → entry
cat "$HERE"/wgsl/apde_common.wgsl \
    "$HERE"/wgsl/apde_bindings.wgsl \
    "$HERE"/wgsl/apde_geom.wgsl \
    "$HERE"/wgsl/apde_rand.wgsl \
    "$HERE"/wgsl/apde_geomcons.wgsl \
    "$HERE"/wgsl/apde_ncc.wgsl > "$OUT/apde.wgsl"

cat >> "$OUT/apde.wgsl" <<'ENTRY'

@compute @workgroup_size(16, 16)
fn ncc_bench(@builtin(global_invocation_id) gid : vec3<u32>) {
  if (gid.x >= P.width || gid.y >= P.height) { return; }
  let p = vec2<i32>(i32(gid.x), i32(gid.y));
  var acc = 0.0;
  for (var r : u32 = 0u; r < max(P.iter, 1u); r = r + 1u) {
    acc = acc + compute_bilateral_ncc(p, cams[0], cams[1 + (r % 4u)],
                                      vec4<f32>(0.0, 0.0, -1.0, 2.0 + f32(r) * 0.01));
  }
  costs[gid.y * P.width + gid.x] = acc / f32(max(P.iter, 1u));
}
ENTRY

naga "$OUT/apde.wgsl"                                    # 验证
naga "$OUT/apde.wgsl" "$OUT/apde.spv"                    # → SPIR-V (Android/鸿蒙)
spirv-cross "$OUT/apde.spv" --msl --msl-version 20300 \
            --output "$OUT/apde.metal"                   # → MSL (iOS/macOS)
xcrun -sdk macosx metal -c "$OUT/apde.metal" -o "$OUT/apde.air"
xcrun -sdk macosx metallib "$OUT/apde.air" -o "$OUT/apde.metallib"
clang++ -std=c++17 -fobjc-arc -O2 "$HERE"/host/ncc_bench.mm \
        -framework Metal -framework Foundation -o "$OUT/ncc_bench"
echo "OK → $OUT/{apde.spv,apde.metallib,ncc_bench}"
