#!/bin/bash
# 编 MVS-Texturing (texrecon)。四个依赖全部钉到 2026-09-22 审计过的精确 SHA ——
# 上游 elibs/CMakeLists.txt 的 ext_rayint 钉的是分支名、ext_mve 根本没有 GIT_TAG,
# 照抄上游会编到与审计不同的代码。
set -eu
R=/root/texrecon_build
MVST=f3374298ac959cb5afe47a14e4d35d2ac7fbdbb1
MVE=91c0f3fde0781399b2fe872d8e52e4899274a84a
RAYINT=b62c8905f6dd11a179128517e814e0e00f9bb809
MAPMAP=fa526e0963ca3e431a02aa7b9e87b85ba8a8e304
log(){ echo "[$(date +%H:%M:%S)] $*"; }
rm -rf $R; mkdir -p $R; cd $R
log '拉 mvs-texturing'
git clone -q https://github.com/nmoehrle/mvs-texturing.git src && git -C src checkout -q $MVST
log '按审计 SHA 预置四个依赖(绕开上游的浮动引用)'
mkdir -p src/elibs
git clone -q https://github.com/nmoehrle/mve.git src/elibs/mve && git -C src/elibs/mve checkout -q $MVE
git clone -q https://github.com/nmoehrle/rayint.git src/elibs/rayint && git -C src/elibs/rayint checkout -q $RAYINT
git clone -q https://github.com/dthuerck/mapmap_cpu.git src/elibs/mapmap && git -C src/elibs/mapmap checkout -q $MAPMAP
curl -sL https://gitlab.com/libeigen/eigen/-/archive/3.3.2/eigen-3.3.2.tar.gz -o eigen.tgz
mkdir -p src/elibs/eigen && tar xzf eigen.tgz -C src/elibs/eigen --strip-components=1
log '义务 3:剔掉带专利声明的 libs/sfm(不参编,删了自证)'
rm -rf src/elibs/mve/libs/sfm
log '自证四个 revision'
for d in src src/elibs/mve src/elibs/rayint src/elibs/mapmap; do printf '  %-24s %s\n' $d "$(git -C $d rev-parse HEAD)"; done
log '编 MVE 的两个库(只这两个)'
make -C src/elibs/mve/libs/mve -j8 >/dev/null 2>&1 && make -C src/elibs/mve/libs/util -j8 >/dev/null 2>&1 && echo '  mve+util OK'
log 'cmake 配置(去掉 elibs 的 externalproject,已预置)'
# 保留 elibs 目标名(texrecon 用 add_dependencies 引用),只把下载动作换成空操作
cat > src/elibs/CMakeLists.txt <<CME
# 依赖已按 2026-09-22 审计的精确 SHA 预置在 elibs/ 下, 这里只保留目标名。
add_custom_target(ext_mve)
add_custom_target(ext_rayint)
add_custom_target(ext_mapmap)
add_custom_target(ext_eigen)
CME
mkdir -p build && cd build
cmake -DCMAKE_BUILD_TYPE=RELEASE ../src > cmake.log 2>&1 || { log 'CMAKE 失败'; tail -25 cmake.log; touch /root/TEXRECON_FAILED; exit 1; }
log '编译'
make -j8 > make.log 2>&1 || { log 'MAKE 失败'; tail -40 make.log; touch /root/TEXRECON_FAILED; exit 1; }
log '产物'; find $R/build -name texrecon -type f -exec ls -la {} \;
touch /root/TEXRECON_DONE
