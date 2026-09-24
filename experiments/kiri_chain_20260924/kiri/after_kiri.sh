#!/bin/bash
cd /root/tsdf_improve/kiri
while ! grep -q "ALL DONE" run_both.log; do sleep 10; done
echo "$(date +%T) colour"
/root/venv_o3d_fix/bin/python color_for_page.py out/kiri_v0.01_t0.04_w5.ply out/kiri_v0.01_col.ply out/kiri_v0.003_t0.04_w5.ply out/kiri_v0.003_col.ply
echo "$(date +%T) chunk"
/root/venv_o3d_fix/bin/python /root/chunk_mesh.py out/kiri_v0.01_col.ply /root/page_cmp/bin K1 6000000 | grep -v "^  块"
/root/venv_o3d_fix/bin/python /root/chunk_mesh.py out/kiri_v0.003_col.ply /root/page_cmp/bin K3 6000000 | grep -v "^  块"
echo "$(date +%T) AFTER DONE"
