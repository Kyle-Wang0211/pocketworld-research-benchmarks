#!/bin/bash
# texrecon step of the KIRI chain, parameters verbatim from GauStudio README @132d749d:
#   texrecon ./images ./fused_mesh.ply ./textured_mesh --outlier_removal=gauss_clamping --data_term=area --no_intermediate_results
# mesh  = KIRI-chain 1cm mesh (out/kiri_v0.01_t0.04_w5.ply, user-chosen); images = our 132 full-res photos + the cameras that
# fused it (/root/tsdf_improve/tex_A/scene, alignment verified <= 1 px on 2026-09-23).
# User decision 2026-09-24: use this default (unseen faces deleted), not --keep_unseen_faces.
B=/root/texrecon_build/build/apps/texrecon/texrecon
/usr/bin/time -f "peak RSS %M KB, wall %e s" $B /root/tsdf_improve/tex_A/scene /root/tsdf_improve/kiri/out/kiri_v0.01_t0.04_w5.ply /root/tsdf_improve/tex_K1/K1_textured --outlier_removal=gauss_clamping --data_term=area --no_intermediate_results
echo "rc=$?"
