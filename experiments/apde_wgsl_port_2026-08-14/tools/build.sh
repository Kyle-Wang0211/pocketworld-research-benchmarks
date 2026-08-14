#!/usr/bin/env bash
# APDe-MVS WGSL 移植:构建 + 打点
# 依赖:brew install naga-cli spirv-cross glslang  + Xcode(metal 编译器)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-/tmp/apde_build}"
mkdir -p "$OUT"

# ⚠️ 拼接顺序是契约,不能改。WGSL 要求被调用者先声明,顺序即依赖图:
#   common → bindings → geom → rand → geomcons → ncc → refine → init →
#   propagate → weak → depth2weak → anchors → ncc_new → weak_prop → ransac → entries
# 其中 ncc_new 必须在 anchors 之后(用 ANCHOR_NUM/打包约定),
# weak_prop 必须在 ncc_new 之后(调 compute_bilateral_ncc_new),
# ransac 必须在 anchors 之后(用 point_in_triangle)与 ncc_new 之后(用 get_anchor_point)。
cat "$HERE"/wgsl/apde_common.wgsl \
    "$HERE"/wgsl/apde_bindings.wgsl \
    "$HERE"/wgsl/apde_geom.wgsl \
    "$HERE"/wgsl/apde_rand.wgsl \
    "$HERE"/wgsl/apde_geomcons.wgsl \
    "$HERE"/wgsl/apde_ncc.wgsl \
    "$HERE"/wgsl/apde_refine.wgsl \
    "$HERE"/wgsl/apde_init.wgsl \
    "$HERE"/wgsl/apde_propagate.wgsl \
    "$HERE"/wgsl/apde_weak.wgsl \
    "$HERE"/wgsl/apde_depth2weak.wgsl \
    "$HERE"/wgsl/apde_anchors.wgsl \
    "$HERE"/wgsl/apde_ncc_new.wgsl \
    "$HERE"/wgsl/apde_weak_prop.wgsl \
    "$HERE"/wgsl/apde_ransac.wgsl \
    "$HERE"/wgsl/apde_entries.wgsl > "$OUT/apde.wgsl"


naga "$OUT/apde.wgsl"                                    # 验证
naga "$OUT/apde.wgsl" "$OUT/apde.spv"                    # → SPIR-V (Android/鸿蒙)
# 🔴 spirv-cross 每次只出一个 entry point(官方:"By default, the first entry
#    point in the module is used")⇒ 多 kernel 必须逐个 --entry,再一起链接。
ENTRIES=$(awk '/^@compute/{getline; sub(/^fn /,""); sub(/\(.*/,""); print}' "$OUT/apde.wgsl")
echo "entry points: $ENTRIES"
rm -f "$OUT"/k_*.metal "$OUT"/k_*.air
for K in $ENTRIES; do
  spirv-cross "$OUT/apde.spv" --msl --msl-version 20300 --entry "$K" --stage comp \
              --output "$OUT/k_$K.metal"
  xcrun -sdk macosx metal -c "$OUT/k_$K.metal" -o "$OUT/k_$K.air"
done
xcrun -sdk macosx metallib "$OUT"/k_*.air -o "$OUT/apde.metallib"

# 🔴 per-kernel binding remap 表 —— 不是可选项。
#    naga/spirv-cross 会剥掉 kernel 未使用的 binding 并紧凑重编号,
#    host 若按固定 index 绑就会读错 buffer(不报错,只是结果错)。
python3 "$HERE/tools/gen_binding_map.py" "$OUT/apde.wgsl" "$OUT/bindings.json"
clang++ -std=c++17 -fobjc-arc -O2 "$HERE"/host/ncc_bench.mm \
        -framework Metal -framework Foundation -o "$OUT/ncc_bench"
clang++ -std=c++17 -fobjc-arc -O2 "$HERE"/host/occupancy_probe.mm \
        -framework Metal -framework Foundation -o "$OUT/occupancy_probe"
echo "OK → $OUT/{apde.spv,apde.metallib,ncc_bench}"
