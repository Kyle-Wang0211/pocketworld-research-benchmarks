#!/bin/bash
set -e
cd /root/tsdf_improve/kiri
./venv/bin/python /root/vggt_eval/fuse_vggt.py
/root/venv_o3d_fix/bin/python color_for_page.py out/vggt_v0.01_t0.04_w5.ply out/vggt_v0.01_col.ply
/root/venv_o3d_fix/bin/python /root/chunk_mesh.py out/vggt_v0.01_col.ply /root/page_cmp/bin V1 6000000 | grep -v "^  块"
echo "AFTER DONE $(date +%T)"
