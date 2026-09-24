#!/bin/bash
# 三档同分辨率 (1280x720, Infinigen 原生宽高比, 避开 4:3 覆盖引发的相机传感器报错) 公平对照:
#   A 8192 采样 无去噪  = Infinigen 出厂默认
#   B  256 采样 无去噪
#   C  256 采样 + 去噪
set -u
LOG(){ echo "[$(date +%H:%M:%S)] $*"; }
P=/root/ig_venv2/bin/python
cd /root/infinigen
run () {  # $1=tag $2=samples $3=denoise
  local out=/root/ig3/$1
  rm -rf "$out" /root/ig3/frames /root/frames
  local T0=$(date +%s)
  timeout 2400 $P -m infinigen_examples.generate_indoors --seed 0 --task render \
    --input_folder /root/ig_probe/coarse --output_folder "$out" \
    -g fast_solve.gin singleroom.gin \
    -p compose_indoors.terrain_enabled=False \
       configure_render_cycles.num_samples=$2 \
       configure_render_cycles.denoise=$3 \
    > /root/ig3_$1.log 2>&1
  local RC=$? T1=$(date +%s)
  local BT=$(grep -oE '^Time: [0-9:.]+' /root/ig3_$1.log | tail -1)
  LOG "  $1 (samples=$2 denoise=$3) rc=$RC 脚本 $((T1-T0))s | Blender $BT"
  # 🔴 Infinigen 的整理步骤把图移到 <out 的父目录>/frames/Image/camera_0/, 各次互相覆盖
  #    => 每跑完立刻拷走
  local F=""
  for c in /root/ig3/frames/Image/camera_0/Image_*.png /root/frames/Image/camera_0/Image_*.png "$out"/Image_*.png; do
    [ -f "$c" ] && { F="$c"; break; }
  done
  if [ -n "$F" ]; then cp "$F" /root/ig3_$1.png; echo "      -> /root/ig3_$1.png ($(du -h /root/ig3_$1.png | cut -f1))"; else echo "      🔴 没找到图"; fi
}
mkdir -p /root/ig3
LOG "三档渲染 (同 1280x720)"
run s8192_nd 8192 False
run s256_nd   256 False
run s256_dn   256 True
LOG "拼图 + 量噪点"
/venv/main/bin/python - <<'PY'
import cv2, numpy as np, os
items=[("8192 samples  no denoise  (Infinigen default)","/root/ig3_s8192_nd.png"),
       ("256 samples   no denoise","/root/ig3_s256_nd.png"),
       ("256 samples   DENOISE ON","/root/ig3_s256_dn.png")]
outs=[]
for tag,f in items:
    if not os.path.exists(f):
        print("  缺", f); continue
    im=cv2.imread(f)
    g=cv2.cvtColor(im,cv2.COLOR_BGR2GRAY).astype(np.float32)/255
    h,w=g.shape; bs=64
    s=g[:h//bs*bs,:w//bs*bs].reshape(h//bs,bs,w//bs,bs).transpose(0,2,1,3).reshape(-1,bs*bs)
    nf=float(np.percentile(s.std(1),1))
    print("  %-48s %s  噪声地板 %.5f" % (tag, im.shape[:2], nf))
    im=cv2.resize(im,(680,int(680*im.shape[0]/im.shape[1])))
    cv2.rectangle(im,(0,0),(430,30),(0,0,0),-1)
    cv2.putText(im,"%s  nf=%.4f"%(tag.split("  ")[0]+" "+("denoise ON" if "DENOISE" in tag else "no denoise"),nf),
                (6,21),cv2.FONT_HERSHEY_SIMPLEX,0.52,(255,255,255),1,cv2.LINE_AA)
    outs.append(im)
if outs:
    h=min(o.shape[0] for o in outs)
    cv2.imwrite("/root/ig3_cmp.png", np.hstack([o[:h] for o in outs]))
    print("  拼好 /root/ig3_cmp.png")
PY
touch /root/IG3_DONE
