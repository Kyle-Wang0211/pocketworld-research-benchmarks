G="/venv/main/bin/python /root/afsr_tools/geom.py"
$G /root/av_ep0_off/A_filt/mesh.obj "基线 A_filt(Delaunay)"
$G /root/afsr/out/p2M_off.ply  "2M_off 阴性对照"
$G /root/afsr/out/p2M_post.ply "2M_post 后过滤"
$G /root/afsr/out/p2M_pre.ply  "2M_pre 前过滤"
$G /root/afsr/out/p2M_off_crop.ply  "2M_off 裁A盒"
$G /root/afsr/out/p2M_post_crop.ply "2M_post 裁A盒"
$G /root/afsr/out/p2M_pre_crop.ply  "2M_pre 裁A盒"
$G /root/afsr/out/p200k_off.ply  "200k_off"
$G /root/afsr/out/p200k_post.ply "200k_post"
$G /root/afsr/out/p200k_pre.ply  "200k_pre"
for f in /root/afsr/sweep/*.ply; do $G $f "sweep_$(basename $f .ply)"; done
echo GEOM_DONE
