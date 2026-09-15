#!/bin/bash
# cv2 (OpenCV 4.13.0 = the pip wheel's tag) Python bindings rebuilt with -ffp-contract=off,
# so the Python reference rounds exactly like every device OpenCV build:
#   opencv-pw/scripts/pw_opencv_config.sh   PW_FP_CONTRACT="off"   (5.0.0, iOS+Android)
#   opencv-401-build-mac/CMakeCache.txt      CMAKE_CXX_FLAGS=-ffp-contract=off (4.0.1 host)
# The pip wheel is Apple clang 15 default (-ffp-contract=on): its remap = fma(S3,w3,fma(S2,w2,fma(S0,w0,S1*w1))),
# 21.4% of interpolated pixels differ from the 'off' rounding by 1 ULP (measured 2026-09-15).
# HAL/LAPACK/etc. off to mirror pw_opencv_config.sh PW_DISABLE_FEATURES.
set -uo pipefail
ROOT=$HOME/Developer/opencv-4130-pyoff
mkdir -p "$ROOT"; cd "$ROOT"
PY=$(command -v python3.11)
NP_INC=$($PY -c "import numpy; print(numpy.get_include())")
GEN="Unix Makefiles"; command -v ninja >/dev/null 2>&1 && GEN=Ninja
echo "[$(date +%H:%M:%S)] python=$PY numpy_inc=$NP_INC generator=$GEN"
if [ ! -f opencv-4.13.0.tar.gz ]; then
  curl -sSL --max-time 900 -o opencv-4.13.0.tar.gz https://github.com/opencv/opencv/archive/refs/tags/4.13.0.tar.gz || { echo "DOWNLOAD_FAIL"; exit 1; }
fi
ls -la opencv-4.13.0.tar.gz
[ -d opencv-4.13.0 ] || tar xzf opencv-4.13.0.tar.gz
grep -E "define CV_VERSION_(MAJOR|MINOR|REVISION)" opencv-4.13.0/modules/core/include/opencv2/core/version.hpp
echo "[$(date +%H:%M:%S)] configure"
cmake -S opencv-4.13.0 -B build -G "$GEN" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_LIST=core,imgproc,python3 \
  -DCMAKE_C_FLAGS=-ffp-contract=off -DCMAKE_CXX_FLAGS=-ffp-contract=off \
  -DWITH_LAPACK=OFF -DWITH_EIGEN=OFF -DWITH_IPP=OFF -DWITH_OPENCL=OFF -DWITH_KLEIDICV=OFF -DWITH_CAROTENE=OFF \
  -DWITH_ITT=OFF -DWITH_PROTOBUF=OFF -DWITH_ADE=OFF -DWITH_OBSENSOR=OFF -DWITH_TBB=OFF -DWITH_OPENMP=OFF \
  -DWITH_PNG=OFF -DWITH_JPEG=OFF -DWITH_TIFF=OFF -DWITH_WEBP=OFF -DWITH_OPENEXR=OFF -DWITH_OPENJPEG=OFF -DWITH_JASPER=OFF -DWITH_AVIF=OFF \
  -DBUILD_TESTS=OFF -DBUILD_PERF_TESTS=OFF -DBUILD_EXAMPLES=OFF -DBUILD_opencv_apps=OFF -DBUILD_DOCS=OFF -DBUILD_JAVA=OFF -DBUILD_ZLIB=ON \
  -DPYTHON3_EXECUTABLE="$PY" -DPYTHON3_NUMPY_INCLUDE_DIRS="$NP_INC" -DBUILD_opencv_python3=ON \
  -DOPENCV_PYTHON3_INSTALL_PATH="$ROOT/pylib" -DOPENCV_SKIP_PYTHON_LOADER=ON \
  -DCMAKE_INSTALL_PREFIX="$ROOT/install" > build_configure.log 2>&1 || { echo "CONFIGURE_FAIL"; tail -40 build_configure.log; exit 1; }
grep -E "C\+\+ flags \(Release\)|Custom HAL|Parallel framework|OpenCV modules:|To be built|Python 3:|numpy:|Baseline|Dispatched" build_configure.log
echo "[$(date +%H:%M:%S)] build (-j3, 18GB machine rule)"
cmake --build build -j3 > build_compile.log 2>&1 || { echo "BUILD_FAIL"; grep -n "error" build_compile.log | head -20; exit 1; }
cmake --install build > build_install.log 2>&1 || { echo "INSTALL_FAIL"; tail -20 build_install.log; exit 1; }
echo "[$(date +%H:%M:%S)] installed:"; ls -la "$ROOT/pylib"
PYTHONPATH="$ROOT/pylib" "$PY" - <<'EOF'
import cv2, numpy as np
print("cv2", cv2.__version__, cv2.__file__)
bi = cv2.getBuildInformation()
for l in bi.splitlines():
    if any(k in l for k in ("C++ flags (Release)", "Custom HAL", "Parallel framework", "Baseline", "LAPACK")):
        print("  ", l.strip()[:150])
# self-check: 'off' rounding must equal pure f32 left-to-right on random data (100%), wheel pattern must NOT
rng=np.random.default_rng(0); H,W=64,80
src=rng.random((H,W),np.float32)*10
mx=(rng.random((H,W),np.float32)*(W+4)-2).astype(np.float32); my=(rng.random((H,W),np.float32)*(H+4)-2).astype(np.float32)
ref=cv2.remap(src,mx,my,interpolation=cv2.INTER_LINEAR)
sx=np.round(mx*32).astype(np.int64); sy=np.round(my*32).astype(np.int64)
ix=sx>>5; iy=sy>>5; fx=((sx&31)/np.float32(32)).astype(np.float32); fy=((sy&31)/np.float32(32)).astype(np.float32)
one=np.float32(1); w=[(one-fy)*(one-fx),(one-fy)*fx,fy*(one-fx),fy*fx]
def px(x,y):
    ok=(x>=0)&(x<W)&(y>=0)&(y<H); v=np.zeros_like(src); v[ok]=src[y[ok],x[ok]]; return v
S=[px(ix,iy),px(ix+1,iy),px(ix,iy+1),px(ix+1,iy+1)]
off=(((S[0]*w[0]+S[1]*w[1])+S[2]*w[2])+S[3]*w[3]).astype(np.float32)
print("cv2(off) == pure-f32-left-to-right: %.4f%% (expect 100)" % (100*(off==ref).mean()))
EOF
echo CV2OFF_DONE
