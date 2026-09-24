set -e
export DEBIAN_FRONTEND=noninteractive
apt-get install -y -qq libtiff-dev libjpeg-turbo8-dev libpng-dev libpugixml-dev libfmt-dev \
   libraw-dev libwebp-dev libfreetype-dev libopencolorio-dev libsquish-dev libgif-dev \
   libheif-dev libopenjp2-7-dev libhwy-dev git ninja-build >/dev/null 2>&1 || true
cd /root
if [ ! -d /root/oiio ]; then git clone -q --depth 1 -b v3.0.8.1 https://github.com/AcademySoftwareFoundation/OpenImageIO /root/oiio || git clone -q --depth 1 -b v3.0.8.0 https://github.com/AcademySoftwareFoundation/OpenImageIO /root/oiio; fi
mkdir -p /root/oiio/bld && cd /root/oiio/bld
/root/cmake-3.31.6-linux-x86_64/bin/cmake .. -GNinja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local \
  -DUSE_PYTHON=OFF -DOIIO_BUILD_TESTS=OFF -DOIIO_BUILD_TOOLS=OFF \
  -DUSE_OPENCV=OFF -DUSE_FFMPEG=OFF -DUSE_QT=OFF -DUSE_NUKE=OFF \
  -DOpenImageIO_BUILD_MISSING_DEPS=all -DBUILD_SHARED_LIBS=ON
/root/cmake-3.31.6-linux-x86_64/bin/cmake --build . -j 32
/root/cmake-3.31.6-linux-x86_64/bin/cmake --install .
ldconfig
echo OIIO_INSTALL_OK
