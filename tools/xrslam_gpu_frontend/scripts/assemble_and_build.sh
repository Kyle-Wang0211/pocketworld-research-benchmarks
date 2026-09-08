#!/bin/bash
# 2026-09-09 reconstruction of the script the disk cleanup destroyed. Incremental: rebuild whatever
# changed in the engine tree, assemble the 58-member research archive, receipt it, then build and
# install the bench app.
#
# The archive is core + extra(opencv-image, yaml-config) + interface + localization + yaml-cpp.
# Ceres and OpenCV are NOT in it: the app links those separately.
set -uo pipefail
X=$HOME/Developer/xrslam-4beb1a9-thr; B=$X/build-cleanA
V=$HOME/Developer/pocketworld/vendor/xrslam/libs/ios-arm64
G=$HOME/Developer/viobench-build/gpufe
S=$HOME/.config/superpowers/worktrees/pocketworld_research_benchmarks/basalt-vio-phone-bench-20260829/tools/ios_basalt_vio_bench/scripts
[ -d "$B" ] || { echo "no build tree - run configure_engine.sh first"; exit 1; }
echo "══ 增量重编引擎 ══"
# The dylib target needs the GPU front end's symbols, which only the app link provides; build the
# static libraries and the two loose object dirs instead of the default target.
ninja -C "$B" xrslam-core xrslam-extra-opencv-image xrslam-extra-yaml-config yaml-cpp 2>&1 | tail -3
for t in xrslam-interface/CMakeFiles/xrslam.dir/src/XRSLAMInternal.cpp.o \
         xrslam-interface/CMakeFiles/xrslam.dir/src/XRSLAMManager.cpp.o \
         xrslam-localization/CMakeFiles/xrslam-localization.dir/src/XRGlobalLocalizerInternal.cpp.o \
         xrslam-localization/CMakeFiles/xrslam-localization.dir/src/XRGlobalLocalizerManager.cpp.o; do
  ninja -C "$B" "$t" 2>&1 | grep -E "error:|FAILED" | head -3
done
MISS=0
for t in $B/xrslam/libxrslam-core.a $B/xrslam-extra/libxrslam-extra-opencv-image.a \
         $B/xrslam-extra/libxrslam-extra-yaml-config.a $B/_deps/depends-yaml-cpp-build/libyaml-cpp.a; do
  [ -f "$t" ] || { echo "缺 $t"; MISS=1; }
done
[ "$MISS" = 1 ] && { echo "不归档"; exit 1; }
OBJS=$(find $B/xrslam-interface/CMakeFiles $B/xrslam-localization/CMakeFiles -name "*.cpp.o" | sort)
FINAL=$V/libxrslam_gpufe_4beb1a9.a
OUT=$G/libxrslam_gpufe_4beb1a9.a.new   # verified before it replaces the vendored one
xcrun libtool -static -o "$OUT" \
  $B/xrslam/libxrslam-core.a $B/xrslam-extra/libxrslam-extra-opencv-image.a \
  $B/xrslam-extra/libxrslam-extra-yaml-config.a $B/_deps/depends-yaml-cpp-build/libyaml-cpp.a \
  $OBJS 2>&1 | grep -v "has no symbols" | head -3
N=$(xcrun ar -t "$OUT" | grep -c "\.o$")
# 57 object members; the 58th entry of `ar -t` is __.SYMDEF, which the old receipt counted too.
echo "归档成员 $N (期望 57)  sha16 $(shasum -a256 "$OUT" | cut -c1-16)"
[ "$N" -eq 57 ] || { echo "成员数不对,不归档"; rm -f "$OUT"; exit 1; }
# NB: never `nm | grep -q` under pipefail - grep exits at the first match, nm dies of SIGPIPE, and the
# pipeline reports failure on a SUCCESSFUL check. That misread cost a rebuild cycle on 09-09 and an
# archive on 09-04.
xcrun nm "$OUT" > "$G/.syms.txt" 2>/dev/null
if grep -qE "T _XRSLAMGetPropagatedPose" "$G/.syms.txt"; then echo "ABI: XRSLAMGetPropagatedPose 存在"
else echo "缺 XRSLAMGetPropagatedPose,不装机"; exit 1; fi
mv "$OUT" "$FINAL"; OUT=$FINAL
python3 - "$OUT" <<'PY'
import json,hashlib,subprocess,sys,datetime
out=sys.argv[1]
r=json.load(open(out.replace('.a','.receipt.json')))
r['artifact_sha256']=hashlib.sha256(open(out,'rb').read()).hexdigest()
r['built_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
r['archive_member_count']=int(subprocess.run(['xcrun','ar','-t',out],capture_output=True,text=True).stdout.count('.o'))
r['rebuild_note_zh']=('2026-09-09 磁盘清理删掉了构建树后按回执参数重建。相对 09-05 那版, 未改动的成员不是逐字节相同: '
 '差异是同语义的寄存器分配与栈溢出选择(指令序列等价), 编译器与 SDK 版本均未变, 原因未定位。'
 '因此本次判据改为行为门: 真机回放 AUDIT=1 的 CLAHE/检测逐位审计 + ATE 落在基线带内。')
r['exported_abi']=sorted(set(r.get('exported_abi',[])+['XRSLAMGetPropagatedPose']))
json.dump(r,open(out.replace('.a','.receipt.json'),'w'),indent=1,ensure_ascii=False)
print('receipt updated')
PY
echo "══ 台架 app ══"
"$S/pw_build_gpufe_arm.sh" && "$S/pw_install_arm.sh" gpufe
echo ASSEMBLE_DONE
