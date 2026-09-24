#!/bin/bash
# Same texrecon call as run_tex.sh (GauStudio README params verbatim) + texrecon's own --keep_unseen_faces
# (settings.h:94, default false). With it, faces no view saw and texrecon's hole_filling could not patch are kept
# with a 3x3 zero (black) patch (generate_texture_patches.cpp:565-580) instead of being deleted from the output.
cd /root/tsdf_improve/tex_K1
B=/root/texrecon_build/build/apps/texrecon/texrecon
/usr/bin/time -f "peak RSS %M KB, wall %e s" $B /root/tsdf_improve/tex_A/scene /root/tsdf_improve/kiri/out/kiri_v0.01_t0.04_w5.ply \
  /root/tsdf_improve/tex_K1/K1keep_textured --outlier_removal=gauss_clamping --data_term=area --no_intermediate_results --keep_unseen_faces
echo "keep rc=$?"
/venv/main/bin/python /root/tsdf_improve/tex_K1/after_keep.py
echo KEEP_ALL_DONE
