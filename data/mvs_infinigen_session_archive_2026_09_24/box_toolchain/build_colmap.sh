set -e
cd /root
rm -rf /root/colmap-4.1.0-fa8e3b3
tar xzf /root/colmap-src.tgz
cd /root/colmap-4.1.0-fa8e3b3
mkdir -p build && cd build
cmake .. -GNinja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCUDA_ENABLED=OFF -DGUI_ENABLED=OFF -DTESTS_ENABLED=OFF \
  -DONNX_ENABLED=OFF -DIPO_ENABLED=OFF -DOPENGL_ENABLED=OFF \
  -DCGAL_ENABLED=ON -DCGAL_DIR=/root/cgal6/CGAL-6.0.1/lib/cmake/CGAL \
  -DCMAKE_INSTALL_PREFIX=/root/colmap-install 2>&1 | tail -40
echo "=== CMAKE_DONE ==="
ninja -j32 colmap_main 2>&1 | tail -30 || ninja -j32 2>&1 | tail -40
echo "=== BUILD_DONE ==="
find /root/colmap-4.1.0-fa8e3b3/build -name 'colmap' -type f | head
