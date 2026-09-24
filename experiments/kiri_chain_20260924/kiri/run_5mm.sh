#!/bin/bash
set -e
cd /root/tsdf_improve/kiri
./venv/bin/python kiri_tsdf.py 0.005 out/kiri_v0.005_t0.04_w5.ply 5
./venv/bin/python kiri_tsdf.py 0.005 out/kiri_v0.005_t0.04_w1.25.ply 1.25
/root/venv_o3d_fix/bin/python color_for_page.py out/kiri_v0.005_t0.04_w5.ply out/kiri_v0.005_w5_col.ply out/kiri_v0.005_t0.04_w1.25.ply out/kiri_v0.005_w1.25_col.ply
/root/venv_o3d_fix/bin/python /root/chunk_mesh.py out/kiri_v0.005_w5_col.ply /root/page_cmp/bin K5A 6000000 | tail -1
/root/venv_o3d_fix/bin/python /root/chunk_mesh.py out/kiri_v0.005_w1.25_col.ply /root/page_cmp/bin K5B 6000000 | tail -1
echo "RUN5 DONE"
