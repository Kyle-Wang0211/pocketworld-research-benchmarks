H="/venv/main/bin/python /root/afsr_tools/holes.py"
$H /root/av_ep0_off/A_filt/mesh.obj "基线 A_filt"
$H /root/afsr/out/p2M_off.ply  "2M_off 阴性对照"
$H /root/afsr/out/p2M_post.ply "2M_post 后过滤"
$H /root/afsr/out/p2M_pre.ply  "2M_pre 前过滤"
echo HOLES_DONE
