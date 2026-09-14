#!/bin/bash
# 用户 09-14 批准: 删旧实验目录 + bmvs 里官方 blend.py:96 不读的 _masked.jpg
set -u
cd /root
for d in regionmerge ms off_native ws_colmap_hires ms2 av community MonoMVSNet venv_murre venv_pda off768_true off1536 tg_probe bins_carve bins_hires ws_gc6 ws_gc8 ws_colmap_dense meshroom meshroom.tar.gz openMVS_build bins_mono sp_probe bins_da3 bins_tsdf3mm vdbfusion_src; do
  [ -e "$d" ] && { rm -rf -- "$d" && echo "rm $d"; }
done
N=$(find /root/bmvs/data -name "*_masked.jpg" | wc -l); echo "masked.jpg 数: $N"
find /root/bmvs/data -name "*_masked.jpg" -delete
echo "剩余 masked: $(find /root/bmvs/data -name "*_masked.jpg" | wc -l)"
df -B1 / | tail -1 | awk "{printf \"[done] free=%.1fG\n\", $4/1e9}"
